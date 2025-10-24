# src/imu_joint_angle.py
import numpy as np
from scipy.optimize import minimize

class IMUJointAngle:
    def __init__(self, delta_t=0.1):
        """
        Initialize IMU-based joint angle measurement system
        delta_t: sampling period in seconds
        """
        self.delta_t = delta_t
        self.j1 = None
        self.j2 = None
        self.o1 = None
        self.o2 = None

        self.prev_angle_gyr = 0.0
        self.prev_angle_acc_gyr = 0.0
        self.lambda_filter = 0.01

    def collect_calibration_data(self, imu1_data, imu2_data):
        N = len(imu1_data)
        data = np.zeros((N, 18))
        for i in range(N):
            data[i, 0:3] = [imu1_data[i]['Ax'], imu1_data[i]['Ay'], imu1_data[i]['Az']]
            data[i, 3:6] = [imu1_data[i]['Gx'], imu1_data[i]['Gy'], imu1_data[i]['Gz']]
            data[i, 9:12] = [imu2_data[i]['Ax'], imu2_data[i]['Ay'], imu2_data[i]['Az']]
            data[i, 12:15] = [imu2_data[i]['Gx'], imu2_data[i]['Gy'], imu2_data[i]['Gz']]

        # 5-point stencil for gyro derivatives (safe fallback at edges)
        for i in range(N):
            if i >= 2 and i < N - 2:
                data[i, 6:9] = (data[i-2, 3:6] - 8*data[i-1, 3:6] +
                                8*data[i+1, 3:6] - data[i+2, 3:6]) / (12 * self.delta_t)
                data[i, 15:18] = (data[i-2, 12:15] - 8*data[i-1, 12:15] +
                                  8*data[i+1, 12:15] - data[i+2, 12:15]) / (12 * self.delta_t)
            elif i < 2:
                # forward difference fallback
                data[i, 6:9] = (data[min(N-1, i+1), 3:6] - data[i, 3:6]) / self.delta_t
                data[i, 15:18] = (data[min(N-1, i+1), 12:15] - data[i, 12:15]) / self.delta_t
            else:
                # backward difference fallback
                data[i, 6:9] = (data[i, 3:6] - data[max(0, i-1), 3:6]) / self.delta_t
                data[i, 15:18] = (data[i, 12:15] - data[max(0, i-1), 12:15]) / self.delta_t

        return data

    def identify_joint_axis(self, calibration_data, max_iter=200):
        def sph_to_cart(phi, theta):
            return np.array([np.cos(phi) * np.cos(theta),
                             np.cos(phi) * np.sin(theta),
                             np.sin(phi)])
        def cost_function(params):
            phi1, theta1, phi2, theta2 = params
            j1 = sph_to_cart(phi1, theta1)
            j2 = sph_to_cart(phi2, theta2)
            error = 0.0
            for i in range(len(calibration_data)):
                g1 = calibration_data[i, 3:6]
                g2 = calibration_data[i, 12:15]
                cross1 = np.cross(g1, j1)
                cross2 = np.cross(g2, j2)
                error += (np.linalg.norm(cross1) - np.linalg.norm(cross2))**2
            return error

        x0 = [0.0, 0.0, 0.0, 0.0]
        result = minimize(cost_function, x0, method='BFGS', options={'maxiter': max_iter})
        phi1, theta1, phi2, theta2 = result.x
        self.j1 = sph_to_cart(phi1, theta1)
        self.j2 = sph_to_cart(phi2, theta2)
        self._match_joint_axis_signs(calibration_data)
        return result

    def _match_joint_axis_signs(self, calibration_data):
        min_activity = float('inf')
        min_idx = 0
        for i in range(len(calibration_data)):
            g1 = calibration_data[i, 3:6]
            g2 = calibration_data[i, 12:15]
            activity = abs(np.dot(g1, self.j1)) + abs(np.dot(g2, self.j2))
            if activity < min_activity:
                min_activity = activity
                min_idx = i

        window = 5
        start = max(0, min_idx - window)
        end = min(len(calibration_data), min_idx + window)
        proj1_list = []
        proj2_list = []
        for i in range(start, end):
            g1 = calibration_data[i, 3:6]
            g2 = calibration_data[i, 12:15]
            # Build orthonormal basis for each joint axis
            c = np.array([1.0, 0.0, 0.0])
            x1 = np.cross(self.j1, c)
            if np.linalg.norm(x1) < 1e-6:
                x1 = np.array([0.0, 1.0, 0.0])
            x1 = x1 / np.linalg.norm(x1)
            y1 = np.cross(self.j1, x1)
            x2 = np.cross(self.j2, c)
            if np.linalg.norm(x2) < 1e-6:
                x2 = np.array([0.0, 1.0, 0.0])
            x2 = x2 / np.linalg.norm(x2)
            y2 = np.cross(self.j2, x2)
            proj1 = np.array([np.dot(g1, x1), np.dot(g1, y1)])
            proj2 = np.array([np.dot(g2, x2), np.dot(g2, y2)])
            proj1_list.append(proj1)
            proj2_list.append(proj2)
        proj1_arr = np.array(proj1_list).flatten()
        proj2_arr = np.array(proj2_list).flatten()
        if proj1_arr.size == 0 or proj2_arr.size == 0:
            return
        corr_pos = np.corrcoef(proj1_arr, proj2_arr)[0, 1]
        corr_neg = np.corrcoef(proj1_arr, -proj2_arr)[0, 1]
        if corr_neg > corr_pos:
            self.j2 = -self.j2

    def identify_joint_position(self, calibration_data, max_iter=200):
        def gamma(g, g_dot, o):
            return np.cross(g, np.cross(g, o)) + np.cross(g_dot, o)

        def cost_function(params):
            o1 = params[0:3]
            o2 = params[3:6]
            error = 0.0
            for i in range(len(calibration_data)):
                a1 = calibration_data[i, 0:3]
                g1 = calibration_data[i, 3:6]
                g_dot1 = calibration_data[i, 6:9]
                a2 = calibration_data[i, 9:12]
                g2 = calibration_data[i, 12:15]
                g_dot2 = calibration_data[i, 15:18]
                shifted_a1 = a1 - gamma(g1, g_dot1, o1)
                shifted_a2 = a2 - gamma(g2, g_dot2, o2)
                error += (np.linalg.norm(shifted_a1) - np.linalg.norm(shifted_a2))**2
            return error

        x0 = np.zeros(6) + 0.05
        result = minimize(cost_function, x0, method='BFGS', options={'maxiter': max_iter})
        o1_hat = result.x[0:3]
        o2_hat = result.x[3:6]
        # project to joint axis
        if self.j1 is None or self.j2 is None:
            raise ValueError("Joint axes must be identified first.")
        shift = (np.dot(o1_hat, self.j1) + np.dot(o2_hat, self.j2)) / 2.0
        self.o1 = o1_hat - self.j1 * shift
        self.o2 = o2_hat - self.j2 * shift
        return result

    def calculate_angle(self, imu1_reading, imu2_reading):
        if self.j1 is None or self.j2 is None:
            raise ValueError("Joint axes not identified.")
        a1 = np.array([imu1_reading['Ax'], imu1_reading['Ay'], imu1_reading['Az']])
        g1 = np.array([imu1_reading['Gx'], imu1_reading['Gy'], imu1_reading['Gz']])
        a2 = np.array([imu2_reading['Ax'], imu2_reading['Ay'], imu2_reading['Az']])
        g2 = np.array([imu2_reading['Gx'], imu2_reading['Gy'], imu2_reading['Gz']])

        angle_gyr_increment = (np.dot(g1, self.j1) - np.dot(g2, self.j2)) * self.delta_t
        angle_gyr = self.prev_angle_gyr + angle_gyr_increment

        if self.o1 is not None and self.o2 is not None:
            g_dot1 = np.zeros(3)
            g_dot2 = np.zeros(3)
            gamma1 = np.cross(g1, np.cross(g1, self.o1)) + np.cross(g_dot1, self.o1)
            gamma2 = np.cross(g2, np.cross(g2, self.o2)) + np.cross(g_dot2, self.o2)
            a1_shifted = a1 - gamma1
            a2_shifted = a2 - gamma2

            c = np.array([1.0, 0.0, 0.0])
            x1 = np.cross(self.j1, c)
            if np.linalg.norm(x1) < 1e-6:
                x1 = np.array([0.0, 1.0, 0.0])
            x1 = x1 / np.linalg.norm(x1)
            y1 = np.cross(self.j1, x1)
            x2 = np.cross(self.j2, c)
            if np.linalg.norm(x2) < 1e-6:
                x2 = np.array([0.0, 1.0, 0.0])
            x2 = x2 / np.linalg.norm(x2)
            y2 = np.cross(self.j2, x2)

            p1 = np.array([np.dot(a1_shifted, x1), np.dot(a1_shifted, y1)])
            p2 = np.array([np.dot(a2_shifted, x2), np.dot(a2_shifted, y2)])
            if np.linalg.norm(p1) > 1e-6 and np.linalg.norm(p2) > 1e-6:
                angle_acc = np.degrees(np.arctan2(p1[1], p1[0]) - np.arctan2(p2[1], p2[0]))
            else:
                angle_acc = self.prev_angle_acc_gyr

            angle = (self.lambda_filter * angle_acc +
                     (1 - self.lambda_filter) * (self.prev_angle_acc_gyr + angle_gyr - self.prev_angle_gyr))
        else:
            angle = angle_gyr

        self.prev_angle_gyr = angle_gyr
        self.prev_angle_acc_gyr = angle
        return angle