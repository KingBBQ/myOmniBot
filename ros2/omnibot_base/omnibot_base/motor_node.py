"""omnibot_base - Bruecke zwischen ROS2 und dem Motorknoten auf dem RoboESP32.

Aufgaben, mehr nicht:

  * /cmd_vel entgegennehmen, in Radgeschwindigkeiten und daraus in Promille
    Tastverhaeltnis umrechnen, mit fester Rate ans Board schicken
  * die Telemetrie des Boards zu Odometrie integrieren und /odom sowie die
    Transformation odom -> base_footprint veroeffentlichen
  * merken, wenn das Board stumm wird oder die Fernbedienung uebernimmt

Bewusst *nicht* Aufgabe dieses Knotens: irgendeine Regelung. Es gibt noch keine
Encoder, die Odometrie ist reine Koppelnavigation aus der Kennlinie. Sie driftet
und ist als alleinige Quelle fuer SLAM zu schwach - dafuer kommt rf2o auf den
LIDAR dazu. Siehe DOCUMENTATION.md.
"""

import math

import rclpy
from geometry_msgs.msg import Quaternion, TransformStamped, Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from omnibot_base import kinematics
from omnibot_base.protocol import MotorLink, elapsed_ms, flag_names, parse_telemetry


def yaw_to_quaternion(yaw):
    q = Quaternion()
    q.z = math.sin(0.5 * yaw)
    q.w = math.cos(0.5 * yaw)
    return q


class MotorNode(Node):
    def __init__(self):
        super().__init__("omnibot_base")

        self.declare_parameter("port", "/dev/ttyAMA0")
        self.declare_parameter("baudrate", 115200)
        self.declare_parameter("wheel_separation", 0.170)
        self.declare_parameter("min_duty", kinematics.MIN_DUTY)
        self.declare_parameter("max_duty", kinematics.MAX_DUTY)
        self.declare_parameter("send_rate", 20.0)
        self.declare_parameter("cmd_vel_timeout", 0.5)
        self.declare_parameter("telemetry_timeout", 1.0)
        self.declare_parameter("use_stamped_cmd_vel", False)
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "base_footprint")
        # Koppelnavigation ohne Encoder - die Unsicherheit ist erheblich und
        # gehoert ehrlich in die Kovarianz, sonst vertraut ihr der EKF/SLAM
        # mehr, als sie verdient.
        self.declare_parameter("odom_covariance_xy", 0.05)
        self.declare_parameter("odom_covariance_yaw", 0.10)

        self.wheel_separation = self.get_parameter("wheel_separation").value
        self.min_duty = int(self.get_parameter("min_duty").value)
        self.max_duty = int(self.get_parameter("max_duty").value)
        self.cmd_vel_timeout = self.get_parameter("cmd_vel_timeout").value
        self.telemetry_timeout = self.get_parameter("telemetry_timeout").value
        self.publish_tf = self.get_parameter("publish_tf").value
        self.odom_frame = self.get_parameter("odom_frame").value
        self.base_frame = self.get_parameter("base_frame").value

        port = self.get_parameter("port").value
        baudrate = int(self.get_parameter("baudrate").value)
        self.link = MotorLink(port, baudrate)
        self.get_logger().info("Motorknoten an {} mit {} Baud".format(port, baudrate))

        # Fahrzustand
        self.target_left = 0.0
        self.target_right = 0.0
        self.last_cmd_time = self.get_clock().now()

        # Odometrie
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.last_ms = None
        self.last_telemetry_time = None
        self.was_manual = False
        self.board_silent = False

        self.odom_pub = self.create_publisher(Odometry, "odom", 10)
        self.manual_pub = self.create_publisher(Bool, "~/manual_mode", 10)
        self.tf_broadcaster = TransformBroadcaster(self) if self.publish_tf else None

        if self.get_parameter("use_stamped_cmd_vel").value:
            self.create_subscription(
                TwistStamped, "cmd_vel", self.on_cmd_vel_stamped, 10
            )
        else:
            self.create_subscription(Twist, "cmd_vel", self.on_cmd_vel, 10)

        send_period = 1.0 / float(self.get_parameter("send_rate").value)
        self.create_timer(send_period, self.on_send)
        self.create_timer(0.01, self.on_read)

        self.link.ping()

    # ------------------------------------------------------------------ Eingang

    def on_cmd_vel(self, msg):
        self.apply_twist(msg.linear.x, msg.angular.z)

    def on_cmd_vel_stamped(self, msg):
        self.apply_twist(msg.twist.linear.x, msg.twist.angular.z)

    def apply_twist(self, linear, angular):
        self.target_left, self.target_right = kinematics.wheel_speeds(
            linear, angular, self.wheel_separation
        )
        self.last_cmd_time = self.get_clock().now()

    # -------------------------------------------------------------------- Takt

    def on_send(self):
        """Sollwerte ans Board. Laeuft auch im Stillstand weiter."""
        age = (self.get_clock().now() - self.last_cmd_time).nanoseconds * 1e-9
        if age > self.cmd_vel_timeout:
            # Der Totmann im Board greift nach 0,3 s ohnehin. Hier wird er nur
            # nicht erst provoziert: kein cmd_vel heisst Stillstand, nicht
            # Weiterfahren bis zum Timeout.
            self.target_left = self.target_right = 0.0

        duty_left = kinematics.duty_from_speed(
            self.target_left, self.min_duty, self.max_duty
        )
        duty_right = kinematics.duty_from_speed(
            self.target_right, self.min_duty, self.max_duty
        )
        try:
            self.link.drive(duty_left, duty_right)
        except OSError as err:
            self.get_logger().error("Schreiben auf den Link fehlgeschlagen: {}".format(err))

    def on_read(self):
        try:
            lines = self.link.poll()
        except OSError as err:
            self.get_logger().error("Lesen vom Link fehlgeschlagen: {}".format(err))
            return

        for line in lines:
            if line.startswith("t "):
                telemetry = parse_telemetry(line)
                if telemetry is not None:
                    self.on_telemetry(telemetry)
            elif line.startswith("id "):
                self.get_logger().info("Board meldet sich: {}".format(line))
            elif line.startswith("# "):
                # Diagnosezeilen des Boards: Startbericht und abgefangene
                # Ausnahmen. Die gehoeren sichtbar ins Log - ein "# boot" nach
                # einem Telemetrieausfall ist der Beweis, dass das Board sich
                # neu gestartet hat, und der Grund steht in derselben Zeile.
                self.get_logger().warning("Board: {}".format(line[2:]))
            elif line != "ok":
                self.get_logger().debug("Board: {}".format(line))

        self.check_board_alive()

    # -------------------------------------------------------------- Odometrie

    def on_telemetry(self, telemetry):
        now = self.get_clock().now()
        self.last_telemetry_time = now
        if self.board_silent:
            self.get_logger().info("Board meldet sich wieder.")
            self.board_silent = False

        self.report_mode(telemetry)

        left = kinematics.speed_from_duty(telemetry.duty_left)
        right = kinematics.speed_from_duty(telemetry.duty_right)
        linear, angular = kinematics.body_twist(left, right, self.wheel_separation)

        if self.last_ms is not None:
            dt = elapsed_ms(self.last_ms, telemetry.ms) / 1000.0
            # Nach einer Luecke ist der Weg dazwischen unbekannt. Lieber einen
            # Schritt auslassen als einen erfundenen Sprung integrieren.
            if 0.0 < dt <= 0.5:
                self.x, self.y, self.theta = kinematics.integrate(
                    self.x, self.y, self.theta, linear, angular, dt
                )
        self.last_ms = telemetry.ms

        self.publish_odometry(now, linear, angular)

    def publish_odometry(self, stamp, linear, angular):
        cov_xy = float(self.get_parameter("odom_covariance_xy").value)
        cov_yaw = float(self.get_parameter("odom_covariance_yaw").value)

        msg = Odometry()
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = self.odom_frame
        msg.child_frame_id = self.base_frame
        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        msg.pose.pose.orientation = yaw_to_quaternion(self.theta)
        msg.twist.twist.linear.x = linear
        msg.twist.twist.angular.z = angular
        # Nur die drei Freiheitsgrade, die ein Differentialantrieb hat. Der Rest
        # bleibt auf einem grossen Wert stehen: die Ebene wird nicht verlassen.
        msg.pose.covariance[0] = cov_xy**2
        msg.pose.covariance[7] = cov_xy**2
        msg.pose.covariance[14] = 1e6
        msg.pose.covariance[21] = 1e6
        msg.pose.covariance[28] = 1e6
        msg.pose.covariance[35] = cov_yaw**2
        msg.twist.covariance[0] = cov_xy**2
        msg.twist.covariance[7] = cov_xy**2
        msg.twist.covariance[14] = 1e6
        msg.twist.covariance[21] = 1e6
        msg.twist.covariance[28] = 1e6
        msg.twist.covariance[35] = cov_yaw**2
        self.odom_pub.publish(msg)

        if self.tf_broadcaster is not None:
            tf = TransformStamped()
            tf.header.stamp = msg.header.stamp
            tf.header.frame_id = self.odom_frame
            tf.child_frame_id = self.base_frame
            tf.transform.translation.x = self.x
            tf.transform.translation.y = self.y
            tf.transform.rotation = msg.pose.pose.orientation
            self.tf_broadcaster.sendTransform(tf)

    # ----------------------------------------------------------------- Zustand

    def report_mode(self, telemetry):
        """Handbetrieb sichtbar machen - sonst sucht man den Fehler woanders."""
        if telemetry.manual != self.was_manual:
            if telemetry.manual:
                self.get_logger().warning(
                    "Handbetrieb: die Fernbedienung faehrt, /cmd_vel wird "
                    "verworfen. Zurueck nur ueber deren Start/Stop-Taste."
                )
            else:
                self.get_logger().info("Handbetrieb aus - /cmd_vel wirkt wieder.")
            self.was_manual = telemetry.manual
            self.manual_pub.publish(Bool(data=telemetry.manual))

        if telemetry.deadman:
            self.get_logger().warning(
                "Board hat wegen Totmannschaltung gestoppt (Flags: {})".format(
                    " ".join(flag_names(telemetry.flags))
                )
            )

    def check_board_alive(self):
        """Der Motorknoten haengt sich gelegentlich auf - das darf nicht stumm
        bleiben. Siehe den offenen Fehler in TODO.md."""
        if self.last_telemetry_time is None or self.board_silent:
            return
        age = (self.get_clock().now() - self.last_telemetry_time).nanoseconds * 1e-9
        if age > self.telemetry_timeout:
            self.board_silent = True
            self.get_logger().error(
                "Seit {:.1f} s keine Telemetrie - Board haengt vermutlich. "
                "Odometrie ist ab jetzt ungueltig, Reset am ESP32 noetig.".format(age)
            )

    def shutdown(self):
        try:
            self.link.close()
        except Exception as err:  # noqa - beim Beenden darf nichts mehr werfen
            self.get_logger().warning("Link liess sich nicht sauber schliessen: {}".format(err))


def main(args=None):
    rclpy.init(args=args)
    node = MotorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
