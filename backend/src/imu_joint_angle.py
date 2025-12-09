
# src/imu_joint_angle.py
import numpy as np
from scipy.optimize import least_squares

def sph_to_cart(phi, theta):
    """Convert spherical angles (phi,theta) to cartesian unit vector."""
    return np.array([
        np.cos(theta) * np.cos(phi),
        np.cos(theta) * np.sin(phi),
        np.sin(theta)
    ])

def wrap_rad(x):
    """Wrap angles to [-pi, pi]."""
    return (x + np.pi) % (2 * np.pi) - np.pi

class IMUJointAngle:
    def __init__(self, delta_t=0.1, alpha=0.92, adaptive_alpha=True,
                 output_smooth_alpha=0.12, persist_path=None, debug=False):
        self.delta_t = float(delta_t)
        self.alpha = float(alpha)
        self.adaptive_alpha = bool(adaptive_alpha)
        self.output_smooth_alpha = float(output_smooth_alpha)
        self.persist_path = persist_path
        self.debug = bool(debug)

        # calibration results
        self.j1 = None
        self.j2 = None
        self.o1 = None
        self.o2 = None
        self.g1_bias = np.zeros(3)
        self.g2_bias = np.zeros(3)

        # runtime state
        self.prev_angle = 0.0  # radians
        self.zero_offset = 0.0  # radians
        self._smoothed_angle = 0.0  # radians

        # gyro scale (1.0 => rad/s; pi/180 => deg/s -> rad/s)
        self.gyro_scale = 1.0

    # ----------------- Calibration helpers -----------------
    def collect_calibration_data(self, imu1_list, imu2_list):
        """
        Build Nx18 array expected by calibrate/_estimate_offsets.
        Layout:
          0-2   IMU1 accel (Ax,Ay,Az)
          3-5   IMU1 gyro  (Gx,Gy,Gz)
          6-8   IMU1 mag   (placeholders)
          9-11  IMU2 accel
          12-14 IMU2 gyro
          15-17 IMU2 mag
        """
        if imu1_list is None or imu2_list is None:
            raise ValueError("imu1_list and imu2_list required")
        n = min(len(imu1_list), len(imu2_list))
        arr = np.zeros((n, 18), dtype=float)
        for i in range(n):
            i1 = imu1_list[i]
            i2 = imu2_list[i]

            arr[i, 0] = float(i1.get('Ax', i1.get('ax', 0.0)))
            arr[i, 1] = float(i1.get('Ay', i1.get('ay', 0.0)))
            arr[i, 2] = float(i1.get('Az', i1.get('az', 0.0)))

            arr[i, 3] = float(i1.get('Gx', i1.get('gx', 0.0)))
            arr[i, 4] = float(i1.get('Gy', i1.get('gy', 0.0)))
            arr[i, 5] = float(i1.get('Gz', i1.get('gz', 0.0)))

            arr[i, 6] = float(i1.get('Mx', 0.0))
            arr[i, 7] = float(i1.get('My', 0.0))
            arr[i, 8] = float(i1.get('Mz', 0.0))

            arr[i, 9] = float(i2.get('Ax', i2.get('ax', 0.0)))
            arr[i,10] = float(i2.get('Ay', i2.get('ay', 0.0)))
            arr[i,11] = float(i2.get('Az', i2.get('az', 0.0)))

            arr[i,12] = float(i2.get('Gx', i2.get('gx', 0.0)))
            arr[i,13] = float(i2.get('Gy', i2.get('gy', 0.0)))
            arr[i,14] = float(i2.get('Gz', i2.get('gz', 0.0)))

            arr[i,15] = float(i2.get('Mx', 0.0))
            arr[i,16] = float(i2.get('My', 0.0))
            arr[i,17] = float(i2.get('Mz', 0.0))
        return arr

    def calibrate(self, calibration_data, n_restarts=5):
        """Estimate hinge axes (j1,j2), offsets (o1,o2), and gyro biases from calibration_data (Nx18)."""
        if calibration_data is None or calibration_data.shape[0] < 6:
            raise ValueError("Not enough calibration samples")

        def residuals_axis(params):
            phi1, theta1, phi2, theta2 = params
            j1 = sph_to_cart(phi1, theta1)
            j2 = sph_to_cart(phi2, theta2)
            res = []
            for i in range(calibration_data.shape[0]):
                g1 = calibration_data[i, 3:6]
                g2 = calibration_data[i, 12:15]
                res.append(np.linalg.norm(np.cross(g1, j1)) - np.linalg.norm(np.cross(g2, j2)))
            return np.array(res)

        best_cost = np.inf
        best_j1 = best_j2 = None
        for _ in range(n_restarts):
            x0 = np.random.uniform(-np.pi, np.pi, 4)
            try:
                res = least_squares(residuals_axis, x0, loss='soft_l1', max_nfev=2000)
            except Exception:
                continue
            if res.cost < best_cost:
                best_cost = res.cost
                phi1, theta1, phi2, theta2 = res.x
                best_j1, best_j2 = sph_to_cart(phi1, theta1), sph_to_cart(phi2, theta2)

        if best_j1 is None or best_j2 is None:
            raise RuntimeError("Axis optimization failed")
        self.j1 = best_j1 / np.linalg.norm(best_j1)
        self.j2 = best_j2 / np.linalg.norm(best_j2)
        if np.dot(self.j1, self.j2) < 0:
            self.j2 = -self.j2

        # gyro biases: median (robust)
        try:
            self.g1_bias = np.median(calibration_data[:, 3:6], axis=0)
            self.g2_bias = np.median(calibration_data[:, 12:15], axis=0)
        except Exception:
            self.g1_bias = np.zeros(3)
            self.g2_bias = np.zeros(3)

        # offsets estimation
        try:
            self.o1, self.o2 = self._estimate_offsets(calibration_data)
        except Exception:
            self.o1 = None
            self.o2 = None

    def _estimate_offsets(self, data):
        """Estimate lever-arm offsets o1, o2 with least squares."""
        def residuals_offset(params):
            o1 = params[0:3]
            o2 = params[3:6]
            res = []
            for i in range(data.shape[0]):
                a1 = data[i, 0:3]
                g1 = data[i, 3:6] - self.g1_bias
                a2 = data[i, 9:12]
                g2 = data[i, 12:15] - self.g2_bias
                term1 = a1 - (np.cross(g1, np.cross(g1, o1)))
                term2 = a2 - (np.cross(g2, np.cross(g2, o2)))
                res.append(term1 - term2)
            return np.concatenate(res)

        x0 = np.zeros(6)
        res = least_squares(residuals_offset, x0, loss='soft_l1', max_nfev=2000)
        return res.x[0:3], res.x[3:6]

    # ----------------- persistence -----------------
    def save_calibration(self, path=None):
        p = path if path is not None else self.persist_path
        if p is None:
            raise ValueError("persist_path not set")
        np.savez(p,
                 j1=self.j1, j2=self.j2,
                 o1=self.o1, o2=self.o2,
                 g1_bias=self.g1_bias, g2_bias=self.g2_bias,
                 gyro_scale=self.gyro_scale,
                 zero_offset=self.zero_offset)
        if self.debug:
            print(f"[debug] calibration saved to {p}")

    def load_calibration(self, path=None, load_zero=True):
        p = path if path is not None else self.persist_path
        if p is None:
            return False
        try:
            data = np.load(p, allow_pickle=True)
            self.j1 = data.get('j1', None)
            self.j2 = data.get('j2', None)
            self.o1 = data.get('o1', None)
            self.o2 = data.get('o2', None)
            self.g1_bias = data.get('g1_bias', np.zeros(3))
            self.g2_bias = data.get('g2_bias', np.zeros(3))
            self.gyro_scale = float(data.get('gyro_scale', 1.0))
            if load_zero:
                self.zero_offset = float(data.get('zero_offset', 0.0))
                self.prev_angle = self.zero_offset
                self._smoothed_angle = self.zero_offset
            if self.debug:
                print(f"[debug] loaded calibration from {p}")
            return True
        except Exception as e:
            if self.debug:
                print(f"[debug] failed to load calibration: {e}")
            return False

    # ----------------- gyro unit detection -----------------
    def detect_and_set_gyro_scale_from_calib(self, imu1_list, imu2_list, threshold_deg_per_s=20.0):
        """Heuristic: if median gyro magnitude > threshold (deg/s approx) assume deg/s and set scale."""
        try:
            mags = []
            for r1, r2 in zip(imu1_list, imu2_list):
                g1 = np.array([r1['Gx'], r1['Gy'], r1['Gz']], dtype=float)
                g2 = np.array([r2['Gx'], r2['Gy'], r2['Gz']], dtype=float)
                mags.append(np.linalg.norm(g1))
                mags.append(np.linalg.norm(g2))
            med = float(np.median(mags))
            if self.debug:
                print(f"[debug] median gyro mag (raw) = {med:.3f}")
            if med > threshold_deg_per_s:
                self.gyro_scale = np.pi / 180.0
                if self.debug:
                    print("[debug] applying deg->rad gyro scale")
                return True
            else:
                self.gyro_scale = 1.0
                if self.debug:
                    print("[debug] assuming rad/s (gyro_scale=1.0)")
                return False
        except Exception as e:
            if self.debug:
                print(f"[debug] gyro scale detection failed: {e}")
            self.gyro_scale = 1.0
            return False

    # ----------------- zeroing helpers -----------------
    def set_zero_reference(self, imu1_reading, imu2_reading):
        """Set current pose as zero using accel-derived angle (or fallback)."""
        ang = self._compute_accel_angle(imu1_reading, imu2_reading)
        if ang is None:
            # fallback: use current filter output
            try:
                ang_deg = self.calculate_angle(imu1_reading, imu2_reading)
                ang = np.radians(ang_deg)
            except Exception:
                ang = 0.0
        self.zero_offset = float(ang)
        self.prev_angle = float(ang)
        self._smoothed_angle = float(ang)
        if self.debug:
            print(f"[debug] zero_offset set to {np.degrees(self.zero_offset):.3f}°")

    def set_zero_reference_from_window(self, imu1_list, imu2_list, gyro_thresh=0.6, use_median=True):
        """
        Given lists of simultaneous imu1/imu2 readings (stillness window), verify stillness and set zero as median accel-angle.
        """
        if imu1_list is None or imu2_list is None or len(imu1_list) == 0:
            raise ValueError("Need non-empty imu1_list/imu2_list")

        g_mags = []
        for r1, r2 in zip(imu1_list, imu2_list):
            g1 = (np.array([r1['Gx'], r1['Gy'], r1['Gz']], dtype=float) - self.g1_bias) * self.gyro_scale
            g2 = (np.array([r2['Gx'], r2['Gy'], r2['Gz']], dtype=float) - self.g2_bias) * self.gyro_scale
            g_mags.append(np.linalg.norm(g1) + np.linalg.norm(g2))
        g_mean = float(np.mean(g_mags))
        if self.debug:
            print(f"[debug] zero-window mean combined gyro mag = {g_mean:.3f}")

        if g_mean > gyro_thresh:
            raise RuntimeError(f"Window not still enough (mean gyro {g_mean:.3f} > {gyro_thresh})")

        angs = []
        for r1, r2 in zip(imu1_list, imu2_list):
            a = self._compute_accel_angle(r1, r2)
            if a is not None:
                angs.append(a)
        if len(angs) == 0:
            raise RuntimeError("No accel-based angles found in window")
        chosen = float(np.median(angs) if use_median else np.mean(angs))
        self.zero_offset = chosen
        self.prev_angle = chosen
        self._smoothed_angle = chosen
        if self.debug:
            print(f"[debug] zero set from window = {np.degrees(chosen):.3f}° (n={len(angs)})")

    def reestimate_gyro_bias_from_window(self, imu1_list, imu2_list):
        """Recompute gyro bias as median across the provided window."""
        if imu1_list is None or imu2_list is None or len(imu1_list) == 0:
            raise ValueError("Need non-empty lists")
        g1 = np.array([np.median([r['Gx'] for r in imu1_list]),
                       np.median([r['Gy'] for r in imu1_list]),
                       np.median([r['Gz'] for r in imu1_list])], dtype=float)
        g2 = np.array([np.median([r['Gx'] for r in imu2_list]),
                       np.median([r['Gy'] for r in imu2_list]),
                       np.median([r['Gz'] for r in imu2_list])], dtype=float)
        self.g1_bias = g1
        self.g2_bias = g2
        if self.debug:
            print(f"[debug] reestimated gyro biases: g1={self.g1_bias}, g2={self.g2_bias}")

    def force_zero_from_accel_window(self, imu1_list, imu2_list, use_median=True):
        """
        Deterministic accel-only median zero from given lists. Useful fallback when offsets/axes uncertain.
        """
        angs = []
        for r1, r2 in zip(imu1_list, imu2_list):
            a1 = np.array([r1.get('Ax', r1.get('ax', 0.0)),
                           r1.get('Ay', r1.get('ay', 0.0)),
                           r1.get('Az', r1.get('az', 0.0))], dtype=float)
            a2 = np.array([r2.get('Ax', r2.get('ax', 0.0)),
                           r2.get('Ay', r2.get('ay', 0.0)),
                           r2.get('Az', r2.get('az', 0.0))], dtype=float)
            n1 = np.linalg.norm(a1); n2 = np.linalg.norm(a2)
            if n1 < 1e-9 or n2 < 1e-9:
                continue
            dot = np.dot(a1, a2) / (n1 * n2)
            dot = float(max(-1.0, min(1.0, dot)))
            angs.append(np.arccos(dot))
        if len(angs) == 0:
            raise RuntimeError("No accel angles available in given window")
        chosen = float(np.median(angs) if use_median else np.mean(angs))
        self.zero_offset = chosen
        self.prev_angle = chosen
        self._smoothed_angle = chosen
        if self.debug:
            print(f"[debug] force_zero_from_accel_window => {np.degrees(chosen):.3f}°")

    def debug_print_calib_samples(self, imu1_list, imu2_list, max_items=6):
        """Quick preview of first samples and median gyro mag."""
        mags = []
        n = min(len(imu1_list), len(imu2_list), max_items)
        for i in range(n):
            r1 = imu1_list[i]; r2 = imu2_list[i]
            print(f"[debug] sample {i}: IMU1.g={[r1.get('Gx'), r1.get('Gy'), r1.get('Gz')]}, IMU2.g={[r2.get('Gx'), r2.get('Gy'), r2.get('Gz')]}")
            mags.append(np.linalg.norm([r1.get('Gx',0.0), r1.get('Gy',0.0), r1.get('Gz',0.0)]))
            mags.append(np.linalg.norm([r2.get('Gx',0.0), r2.get('Gy',0.0), r2.get('Gz',0.0)]))
        if mags:
            print(f"[debug] preview median gyro mag: {np.median(mags):.3f}")

    # ----------------- accel-only angle -----------------
    def _compute_accel_angle(self, imu1_reading, imu2_reading):
        """Compute an accel-only relative angle (radians)."""
        try:
            a1 = np.array([imu1_reading['Ax'], imu1_reading['Ay'], imu1_reading['Az']], dtype=float)
            g1 = (np.array([imu1_reading['Gx'], imu1_reading['Gy'], imu1_reading['Gz']], dtype=float) - self.g1_bias) * self.gyro_scale
            a2 = np.array([imu2_reading['Ax'], imu2_reading['Ay'], imu2_reading['Az']], dtype=float)
            g2 = (np.array([imu2_reading['Gx'], imu2_reading['Gy'], imu2_reading['Gz']], dtype=float) - self.g2_bias) * self.gyro_scale
        except Exception:
            return None

        # fallback: angle between accel vectors
        if self.j1 is None or self.j2 is None or self.o1 is None or self.o2 is None:
            n1 = np.linalg.norm(a1); n2 = np.linalg.norm(a2)
            if n1 < 1e-9 or n2 < 1e-9:
                return None
            dot = np.dot(a1, a2) / (n1 * n2)
            dot = float(max(-1.0, min(1.0, dot)))
            return float(np.arccos(dot))

        # compensate centripetal terms
        a1_shifted = a1 - np.cross(g1, np.cross(g1, self.o1))
        a2_shifted = a2 - np.cross(g2, np.cross(g2, self.o2))

        x1 = np.cross(self.j1, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(x1) < 1e-6:
            x1 = np.cross(self.j1, np.array([0.0, 1.0, 0.0]))
        x1 /= np.linalg.norm(x1)
        y1 = np.cross(self.j1, x1)

        x2 = np.cross(self.j2, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(x2) < 1e-6:
            x2 = np.cross(self.j2, np.array([0.0, 1.0, 0.0]))
        x2 /= np.linalg.norm(x2)
        y2 = np.cross(self.j2, x2)

        p1 = np.array([np.dot(a1_shifted, x1), np.dot(a1_shifted, y1)])
        p2 = np.array([np.dot(a2_shifted, x2), np.dot(a2_shifted, y2)])
        angle_acc = np.arctan2(p1[1], p1[0]) - np.arctan2(p2[1], p2[0])
        return float(wrap_rad(angle_acc))

    # ----------------- runtime angle calculation -----------------
    def calculate_angle(self, imu1_reading, imu2_reading):
        """
        Compute fused angle (degrees). Updates internal prev_angle and smoothed output.
        Returns angle in degrees (float).
        """
        a1 = np.array([imu1_reading['Ax'], imu1_reading['Ay'], imu1_reading['Az']], dtype=float)
        g1 = (np.array([imu1_reading['Gx'], imu1_reading['Gy'], imu1_reading['Gz']], dtype=float) - self.g1_bias) * self.gyro_scale
        a2 = np.array([imu2_reading['Ax'], imu2_reading['Ay'], imu2_reading['Az']], dtype=float)
        g2 = (np.array([imu2_reading['Gx'], imu2_reading['Gy'], imu2_reading['Gz']], dtype=float) - self.g2_bias) * self.gyro_scale

        # gyro integration (project onto hinge axes)
        if self.j1 is None or self.j2 is None:
            angle_gyr_new = self.prev_angle
        else:
            angle_gyr_inc = (np.dot(g1, self.j1) - np.dot(g2, self.j2)) * self.delta_t
            angle_gyr_new = self.prev_angle + angle_gyr_inc

        # accel-based angle (if possible)
        angle_acc = None
        if self.o1 is not None and self.o2 is not None and self.j1 is not None and self.j2 is not None:
            a1_shifted = a1 - np.cross(g1, np.cross(g1, self.o1))
            a2_shifted = a2 - np.cross(g2, np.cross(g2, self.o2))

            x1 = np.cross(self.j1, np.array([1.0, 0.0, 0.0]))
            if np.linalg.norm(x1) < 1e-6:
                x1 = np.cross(self.j1, np.array([0.0, 1.0, 0.0]))
            x1 /= np.linalg.norm(x1)
            y1 = np.cross(self.j1, x1)

            x2 = np.cross(self.j2, np.array([1.0, 0.0, 0.0]))
            if np.linalg.norm(x2) < 1e-6:
                x2 = np.cross(self.j2, np.array([0.0, 1.0, 0.0]))
            x2 /= np.linalg.norm(x2)
            y2 = np.cross(self.j2, x2)

            p1 = np.array([np.dot(a1_shifted, x1), np.dot(a1_shifted, y1)])
            p2 = np.array([np.dot(a2_shifted, x2), np.dot(a2_shifted, y2)])
            angle_acc = wrap_rad(np.arctan2(p1[1], p1[0]) - np.arctan2(p2[1], p2[0]))

        # fusion with adaptive alpha
        if angle_acc is None:
            angle = angle_gyr_new
        else:
            alpha_use = self.alpha
            if self.adaptive_alpha:
                gyro_mag = np.linalg.norm(g1) + np.linalg.norm(g2)
                # if very still, favor accel more
                if gyro_mag < 0.5:
                    alpha_use = min(alpha_use, 0.85)
                elif gyro_mag < 1.5:
                    alpha_use = min(alpha_use, 0.92)
            angle = alpha_use * angle_gyr_new + (1.0 - alpha_use) * angle_acc

        # subtract zero offset and wrap
        angle = wrap_rad(angle - float(self.zero_offset))
        self.prev_angle = angle

        # output smoothing
        self._smoothed_angle = (self.output_smooth_alpha * angle +
                                (1.0 - self.output_smooth_alpha) * self._smoothed_angle)

        return float(np.degrees(self._smoothed_angle))