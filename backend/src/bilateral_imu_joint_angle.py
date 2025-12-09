"""
bilateral_imu_joint_angle.py

Bilateral IMU joint angle calculation for two legs.
Maintains separate calibration and processing for each leg.
"""

import numpy as np
from scipy.optimize import least_squares
from typing import Dict, Any, Tuple, Optional


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


class BilateralIMUJointAngle:
    """
    Handles joint angle calculations for both legs simultaneously.
    Each leg has independent calibration but shared processing logic.
    """
    
    def __init__(self, delta_t=0.1, alpha=0.92, adaptive_alpha=True,
                 output_smooth_alpha=0.12, persist_path_left=None, 
                 persist_path_right=None, debug=False):
        
        # Shared parameters
        self.delta_t = float(delta_t)
        self.alpha = float(alpha)
        self.adaptive_alpha = bool(adaptive_alpha)
        self.output_smooth_alpha = float(output_smooth_alpha)
        self.debug = bool(debug)
        self.gyro_scale = 1.0  # 1.0 for rad/s, pi/180 for deg/s->rad/s
        
        # Left leg calibration
        self.left = {
            'j1': None,  # Thigh hinge axis
            'j2': None,  # Shank hinge axis
            'o1': None,  # Thigh offset
            'o2': None,  # Shank offset
            'g1_bias': np.zeros(3),  # Thigh gyro bias
            'g2_bias': np.zeros(3),  # Shank gyro bias
            'prev_angle': 0.0,
            'zero_offset': 0.0,
            'smoothed_angle': 0.0,
            'persist_path': persist_path_left
        }
        
        # Right leg calibration
        self.right = {
            'j1': None,
            'j2': None,
            'o1': None,
            'o2': None,
            'g1_bias': np.zeros(3),
            'g2_bias': np.zeros(3),
            'prev_angle': 0.0,
            'zero_offset': 0.0,
            'smoothed_angle': 0.0,
            'persist_path': persist_path_right
        }
    
    # ----------------- Bilateral Calibration -----------------
    
    def calibrate_both_legs(self, left_thigh_data, left_shank_data, 
                           right_thigh_data, right_shank_data, n_restarts=5):
        """
        Calibrate both legs simultaneously.
        
        Args:
            left_thigh_data: List of IMU readings from left thigh
            left_shank_data: List of IMU readings from left shank
            right_thigh_data: List of IMU readings from right thigh
            right_shank_data: List of IMU readings from right shank
        """
        
        # Calibrate left leg
        if self.debug:
            print("Calibrating left leg...")
        left_success = self._calibrate_single_leg(
            left_thigh_data, left_shank_data, self.left, "left", n_restarts
        )
        
        # Calibrate right leg
        if self.debug:
            print("Calibrating right leg...")
        right_success = self._calibrate_single_leg(
            right_thigh_data, right_shank_data, self.right, "right", n_restarts
        )
        
        if self.debug:
            print(f"Calibration complete. Left: {left_success}, Right: {right_success}")
        
        return left_success, right_success
    
    def _calibrate_single_leg(self, imu1_list, imu2_list, leg_data, leg_name, n_restarts):
        """Calibrate a single leg (internal method)."""
        
        if not imu1_list or not imu2_list or len(imu1_list) < 6:
            if self.debug:
                print(f"[{leg_name}] Not enough calibration samples")
            return False
        
        # Collect calibration data
        calib_data = self._collect_calibration_data(imu1_list, imu2_list)
        
        try:
            # Estimate hinge axes
            def residuals_axis(params):
                phi1, theta1, phi2, theta2 = params
                j1 = sph_to_cart(phi1, theta1)
                j2 = sph_to_cart(phi2, theta2)
                res = []
                for i in range(calib_data.shape[0]):
                    g1 = calib_data[i, 3:6]
                    g2 = calib_data[i, 12:15]
                    res.append(np.linalg.norm(np.cross(g1, j1)) - 
                              np.linalg.norm(np.cross(g2, j2)))
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
                raise RuntimeError(f"[{leg_name}] Axis optimization failed")
            
            leg_data['j1'] = best_j1 / np.linalg.norm(best_j1)
            leg_data['j2'] = best_j2 / np.linalg.norm(best_j2)
            
            if np.dot(leg_data['j1'], leg_data['j2']) < 0:
                leg_data['j2'] = -leg_data['j2']
            
            # Estimate gyro biases
            leg_data['g1_bias'] = np.median(calib_data[:, 3:6], axis=0)
            leg_data['g2_bias'] = np.median(calib_data[:, 12:15], axis=0)
            
            # Estimate offsets
            leg_data['o1'], leg_data['o2'] = self._estimate_offsets(
                calib_data, leg_data['j1'], leg_data['j2'], 
                leg_data['g1_bias'], leg_data['g2_bias']
            )
            
            if self.debug:
                print(f"[{leg_name}] Calibration successful")
            
            return True
            
        except Exception as e:
            if self.debug:
                print(f"[{leg_name}] Calibration error: {e}")
            return False
    
    def _collect_calibration_data(self, imu1_list, imu2_list):
        """Build calibration data array."""
        n = min(len(imu1_list), len(imu2_list))
        arr = np.zeros((n, 18), dtype=float)
        
        for i in range(n):
            i1 = imu1_list[i]
            i2 = imu2_list[i]
            
            # IMU1 (thigh)
            arr[i, 0:3] = [i1.get('Ax', 0), i1.get('Ay', 0), i1.get('Az', 0)]
            arr[i, 3:6] = [i1.get('Gx', 0), i1.get('Gy', 0), i1.get('Gz', 0)]
            arr[i, 6:9] = [0, 0, 0]  # Magnetometer placeholder
            
            # IMU2 (shank)
            arr[i, 9:12] = [i2.get('Ax', 0), i2.get('Ay', 0), i2.get('Az', 0)]
            arr[i, 12:15] = [i2.get('Gx', 0), i2.get('Gy', 0), i2.get('Gz', 0)]
            arr[i, 15:18] = [0, 0, 0]  # Magnetometer placeholder
        
        return arr
    
    def _estimate_offsets(self, data, j1, j2, g1_bias, g2_bias):
        """Estimate lever-arm offsets."""
        def residuals_offset(params):
            o1 = params[0:3]
            o2 = params[3:6]
            res = []
            for i in range(data.shape[0]):
                a1 = data[i, 0:3]
                g1 = data[i, 3:6] - g1_bias
                a2 = data[i, 9:12]
                g2 = data[i, 12:15] - g2_bias
                term1 = a1 - (np.cross(g1, np.cross(g1, o1)))
                term2 = a2 - (np.cross(g2, np.cross(g2, o2)))
                res.append(term1 - term2)
            return np.concatenate(res)
        
        x0 = np.zeros(6)
        res = least_squares(residuals_offset, x0, loss='soft_l1', max_nfev=2000)
        return res.x[0:3], res.x[3:6]
    
    # ----------------- Zero Reference -----------------
    
    def set_bilateral_zero_reference(self, left_thigh, left_shank, 
                                    right_thigh, right_shank,
                                    gyro_thresh=0.5, use_median=True):
        """
        Set zero reference for both legs from a still position.
        
        Args:
            left_thigh, left_shank, right_thigh, right_shank: Lists of IMU data
            gyro_thresh: Maximum gyro magnitude for stillness detection
        """
        
        # Check stillness
        if not self._check_stillness(left_thigh, left_shank, 
                                    right_thigh, right_shank, gyro_thresh):
            raise RuntimeError("Not still enough for zero reference")
        
        # Set zero for left leg
        left_angles = []
        for lt, ls in zip(left_thigh, left_shank):
            angle = self._compute_accel_angle(lt, ls, self.left)
            if angle is not None:
                left_angles.append(angle)
        
        if left_angles:
            zero = float(np.median(left_angles) if use_median else np.mean(left_angles))
            self.left['zero_offset'] = zero
            self.left['prev_angle'] = zero
            self.left['smoothed_angle'] = zero
            if self.debug:
                print(f"Left leg zero: {np.degrees(zero):.1f}°")
        
        # Set zero for right leg
        right_angles = []
        for rt, rs in zip(right_thigh, right_shank):
            angle = self._compute_accel_angle(rt, rs, self.right)
            if angle is not None:
                right_angles.append(angle)
        
        if right_angles:
            zero = float(np.median(right_angles) if use_median else np.mean(right_angles))
            self.right['zero_offset'] = zero
            self.right['prev_angle'] = zero
            self.right['smoothed_angle'] = zero
            if self.debug:
                print(f"Right leg zero: {np.degrees(zero):.1f}°")
    
    def _check_stillness(self, left_thigh, left_shank, right_thigh, right_shank, threshold):
        """Check if all sensors are still enough."""
        mags = []
        
        for lt, ls, rt, rs in zip(left_thigh, left_shank, right_thigh, right_shank):
            # Left leg gyro magnitudes
            lg1 = np.array([lt.get('Gx', 0), lt.get('Gy', 0), lt.get('Gz', 0)])
            lg2 = np.array([ls.get('Gx', 0), ls.get('Gy', 0), ls.get('Gz', 0)])
            
            # Right leg gyro magnitudes
            rg1 = np.array([rt.get('Gx', 0), rt.get('Gy', 0), rt.get('Gz', 0)])
            rg2 = np.array([rs.get('Gx', 0), rs.get('Gy', 0), rs.get('Gz', 0)])
            
            # Apply biases if available
            if self.left['g1_bias'] is not None:
                lg1 -= self.left['g1_bias']
                lg2 -= self.left['g2_bias']
            if self.right['g1_bias'] is not None:
                rg1 -= self.right['g1_bias']
                rg2 -= self.right['g2_bias']
            
            total_mag = (np.linalg.norm(lg1) + np.linalg.norm(lg2) + 
                        np.linalg.norm(rg1) + np.linalg.norm(rg2))
            mags.append(total_mag)
        
        mean_mag = np.mean(mags)
        if self.debug:
            print(f"Stillness check: mean gyro mag = {mean_mag:.3f} (threshold: {threshold})")
        
        return mean_mag < threshold
    
    # ----------------- Runtime Angle Calculation -----------------
    
    def calculate_bilateral_angles(self, packet_data):
        """
        Calculate angles for both legs from synchronized packet.
        
        Args:
            packet_data: [timestamp, left_thigh, left_shank, right_thigh, right_shank]
        
        Returns:
            Dict with left_angle_deg and right_angle_deg
        """
        
        
        left_thigh = packet_data["left_leg"]["thigh"]
        left_shank = packet_data["left_leg"]["shank"]
        right_thigh = packet_data[ "right_leg"]["thigh"]
        right_shank = packet_data[ "right_leg"]["shank"]
        
        # Calculate left leg angle
        left_angle = self._calculate_single_leg_angle(
            left_thigh, left_shank, self.left
        )
        
        # Calculate right leg angle
        right_angle = self._calculate_single_leg_angle(
            right_thigh, right_shank, self.right
        )
        
        return {
            'left_angle_deg': left_angle,
            'right_angle_deg': right_angle,
            'angle_difference_deg': abs(left_angle - right_angle) if (left_angle and right_angle) else 0
        }
    
    def _calculate_single_leg_angle(self, imu1_reading, imu2_reading, leg_data):
        """Calculate angle for a single leg (internal method)."""
        
        try:
            a1 = np.array([imu1_reading['Ax'], imu1_reading['Ay'], imu1_reading['Az']])
            g1 = (np.array([imu1_reading['Gx'], imu1_reading['Gy'], imu1_reading['Gz']]) - 
                  leg_data['g1_bias']) * self.gyro_scale
            
            a2 = np.array([imu2_reading['Ax'], imu2_reading['Ay'], imu2_reading['Az']])
            g2 = (np.array([imu2_reading['Gx'], imu2_reading['Gy'], imu2_reading['Gz']]) - 
                  leg_data['g2_bias']) * self.gyro_scale
            
            # Gyro integration
            if leg_data['j1'] is None or leg_data['j2'] is None:
                angle_gyr_new = leg_data['prev_angle']
            else:
                angle_gyr_inc = (np.dot(g1, leg_data['j1']) - 
                               np.dot(g2, leg_data['j2'])) * self.delta_t
                angle_gyr_new = leg_data['prev_angle'] + angle_gyr_inc
            
            # Accel-based angle
            angle_acc = self._compute_accel_angle(imu1_reading, imu2_reading, leg_data)
            
            # Fusion
            if angle_acc is None:
                angle = angle_gyr_new
            else:
                alpha_use = self.alpha
                if self.adaptive_alpha:
                    gyro_mag = np.linalg.norm(g1) + np.linalg.norm(g2)
                    if gyro_mag < 0.5:
                        alpha_use = min(alpha_use, 0.85)
                    elif gyro_mag < 1.5:
                        alpha_use = min(alpha_use, 0.92)
                angle = alpha_use * angle_gyr_new + (1.0 - alpha_use) * angle_acc
            
            # Apply zero offset
            angle = wrap_rad(angle - float(leg_data['zero_offset']))
            leg_data['prev_angle'] = angle
            
            # Output smoothing
            leg_data['smoothed_angle'] = (self.output_smooth_alpha * angle +
                                         (1.0 - self.output_smooth_alpha) * leg_data['smoothed_angle'])
            
            return float(np.degrees(leg_data['smoothed_angle']))
            
        except Exception as e:
            if self.debug:
                print(f"Error calculating angle: {e}")
            return None
    
    def _compute_accel_angle(self, imu1_reading, imu2_reading, leg_data):
        """Compute accel-only angle for a leg."""
        
        try:
            a1 = np.array([imu1_reading['Ax'], imu1_reading['Ay'], imu1_reading['Az']])
            a2 = np.array([imu2_reading['Ax'], imu2_reading['Ay'], imu2_reading['Az']])
            
            # Simple fallback if no calibration
            if (leg_data['j1'] is None or leg_data['j2'] is None or 
                leg_data['o1'] is None or leg_data['o2'] is None):
                n1 = np.linalg.norm(a1)
                n2 = np.linalg.norm(a2)
                if n1 < 1e-9 or n2 < 1e-9:
                    return None
                dot = np.dot(a1, a2) / (n1 * n2)
                dot = float(np.clip(dot, -1.0, 1.0))
                return float(np.arccos(dot))
            
            # Full calculation with offsets
            g1 = (np.array([imu1_reading['Gx'], imu1_reading['Gy'], imu1_reading['Gz']]) - 
                  leg_data['g1_bias']) * self.gyro_scale
            g2 = (np.array([imu2_reading['Gx'], imu2_reading['Gy'], imu2_reading['Gz']]) - 
                  leg_data['g2_bias']) * self.gyro_scale
            
            # Compensate centripetal terms
            a1_shifted = a1 - np.cross(g1, np.cross(g1, leg_data['o1']))
            a2_shifted = a2 - np.cross(g2, np.cross(g2, leg_data['o2']))
            
            # Project onto hinge axis planes
            x1 = np.cross(leg_data['j1'], np.array([1.0, 0.0, 0.0]))
            if np.linalg.norm(x1) < 1e-6:
                x1 = np.cross(leg_data['j1'], np.array([0.0, 1.0, 0.0]))
            x1 /= np.linalg.norm(x1)
            y1 = np.cross(leg_data['j1'], x1)
            
            x2 = np.cross(leg_data['j2'], np.array([1.0, 0.0, 0.0]))
            if np.linalg.norm(x2) < 1e-6:
                x2 = np.cross(leg_data['j2'], np.array([0.0, 1.0, 0.0]))
            x2 /= np.linalg.norm(x2)
            y2 = np.cross(leg_data['j2'], x2)
            
            p1 = np.array([np.dot(a1_shifted, x1), np.dot(a1_shifted, y1)])
            p2 = np.array([np.dot(a2_shifted, x2), np.dot(a2_shifted, y2)])
            
            angle_acc = np.arctan2(p1[1], p1[0]) - np.arctan2(p2[1], p2[0])
            return float(wrap_rad(angle_acc))
            
        except Exception:
            return None
    
    # ----------------- Persistence -----------------
    
    def save_bilateral_calibration(self, left_path=None, right_path=None):
        """Save calibration for both legs."""
        
        # Save left leg
        if left_path or self.left['persist_path']:
            path = left_path or self.left['persist_path']
            np.savez(path,
                    j1=self.left['j1'], j2=self.left['j2'],
                    o1=self.left['o1'], o2=self.left['o2'],
                    g1_bias=self.left['g1_bias'], g2_bias=self.left['g2_bias'],
                    gyro_scale=self.gyro_scale,
                    zero_offset=self.left['zero_offset'])
            if self.debug:
                print(f"Left leg calibration saved to {path}")
        
        # Save right leg
        if right_path or self.right['persist_path']:
            path = right_path or self.right['persist_path']
            np.savez(path,
                    j1=self.right['j1'], j2=self.right['j2'],
                    o1=self.right['o1'], o2=self.right['o2'],
                    g1_bias=self.right['g1_bias'], g2_bias=self.right['g2_bias'],
                    gyro_scale=self.gyro_scale,
                    zero_offset=self.right['zero_offset'])
            if self.debug:
                print(f"Right leg calibration saved to {path}")
    
    def load_bilateral_calibration(self, left_path=None, right_path=None, load_zero=True):
        """Load calibration for both legs."""
        
        left_loaded = False
        right_loaded = False
        
        # Load left leg
        if left_path or self.left['persist_path']:
            path = left_path or self.left['persist_path']
            try:
                data = np.load(path, allow_pickle=True)
                self.left['j1'] = data.get('j1')
                self.left['j2'] = data.get('j2')
                self.left['o1'] = data.get('o1')
                self.left['o2'] = data.get('o2')
                self.left['g1_bias'] = data.get('g1_bias', np.zeros(3))
                self.left['g2_bias'] = data.get('g2_bias', np.zeros(3))
                if load_zero:
                    self.left['zero_offset'] = float(data.get('zero_offset', 0.0))
                self.gyro_scale = float(data.get('gyro_scale', 1.0))
                left_loaded = True
                if self.debug:
                    print(f"Left leg calibration loaded from {path}")
            except Exception as e:
                if self.debug:
                    print(f"Failed to load left calibration: {e}")
        
        # Load right leg
        if right_path or self.right['persist_path']:
            path = right_path or self.right['persist_path']
            try:
                data = np.load(path, allow_pickle=True)
                self.right['j1'] = data.get('j1')
                self.right['j2'] = data.get('j2')
                self.right['o1'] = data.get('o1')
                self.right['o2'] = data.get('o2')
                self.right['g1_bias'] = data.get('g1_bias', np.zeros(3))
                self.right['g2_bias'] = data.get('g2_bias', np.zeros(3))
                if load_zero:
                    self.right['zero_offset'] = float(data.get('zero_offset', 0.0))
                self.gyro_scale = float(data.get('gyro_scale', 1.0))
                right_loaded = True
                if self.debug:
                    print(f"Right leg calibration loaded from {path}")
            except Exception as e:
                if self.debug:
                    print(f"Failed to load right calibration: {e}")
        
        return left_loaded, right_loaded
    
    def reestimate_bilateral_gyro_bias(self, left_thigh, left_shank, 
                                      right_thigh, right_shank):
        """Re-estimate gyro biases for both legs."""
        
        # Left leg
        if left_thigh and left_shank:
            self.left['g1_bias'] = np.array([
                np.median([r['Gx'] for r in left_thigh]),
                np.median([r['Gy'] for r in left_thigh]),
                np.median([r['Gz'] for r in left_thigh])
            ])
            self.left['g2_bias'] = np.array([
                np.median([r['Gx'] for r in left_shank]),
                np.median([r['Gy'] for r in left_shank]),
                np.median([r['Gz'] for r in left_shank])
            ])
        
        # Right leg
        if right_thigh and right_shank:
            self.right['g1_bias'] = np.array([
                np.median([r['Gx'] for r in right_thigh]),
                np.median([r['Gy'] for r in right_thigh]),
                np.median([r['Gz'] for r in right_thigh])
            ])
            self.right['g2_bias'] = np.array([
                np.median([r['Gx'] for r in right_shank]),
                np.median([r['Gy'] for r in right_shank]),
                np.median([r['Gz'] for r in right_shank])
            ])
        
        if self.debug:
            print("Bilateral gyro biases re-estimated")