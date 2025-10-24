import numpy as np
from scipy.optimize import minimize
import json

class IMUJointAngle:
    def __init__(self, delta_t=0.1):
        """
        Initialize IMU-based joint angle measurement system
        
        Parameters:
        delta_t: float - sampling period in seconds
        """
        self.delta_t = delta_t
        self.j1 = None  # Joint axis direction in IMU1 frame
        self.j2 = None  # Joint axis direction in IMU2 frame
        self.o1 = None  # Joint position in IMU1 frame
        self.o2 = None  # Joint position in IMU2 frame
        
        # For angle calculation
        self.prev_angle_gyr = 0.0
        self.prev_angle_acc_gyr = 0.0
        self.lambda_filter = 0.01  # Complementary filter weight
        
    def collect_calibration_data(self, imu1_data, imu2_data):
        """
        Collect and format calibration data from IMU readings
        
        Parameters:
        imu1_data: list of dicts - IMU1 readings with Ax, Ay, Az, Gx, Gy, Gz
        imu2_data: list of dicts - IMU2 readings
        
        Returns:
        numpy array of shape (N, 18) containing [a1, g1, g_dot1, a2, g2, g_dot2]
        """
        N = len(imu1_data)
        data = np.zeros((N, 18))
        
        for i in range(N):
            # IMU1: acceleration (0-2), gyro (3-5), gyro_dot (6-8)
            data[i, 0:3] = [imu1_data[i]['Ax'], imu1_data[i]['Ay'], imu1_data[i]['Az']]
            data[i, 3:6] = [imu1_data[i]['Gx'], imu1_data[i]['Gy'], imu1_data[i]['Gz']]
            
            # IMU2: acceleration (9-11), gyro (12-14), gyro_dot (15-17)
            data[i, 9:12] = [imu2_data[i]['Ax'], imu2_data[i]['Ay'], imu2_data[i]['Az']]
            data[i, 12:15] = [imu2_data[i]['Gx'], imu2_data[i]['Gy'], imu2_data[i]['Gz']]
        
        # Calculate gyro derivatives using 5-point stencil
        for i in range(N):
            if i >= 2 and i < N - 2:
                data[i, 6:9] = (data[i-2, 3:6] - 8*data[i-1, 3:6] + 
                               8*data[i+1, 3:6] - data[i+2, 3:6]) / (12 * self.delta_t)
                data[i, 15:18] = (data[i-2, 12:15] - 8*data[i-1, 12:15] + 
                                 8*data[i+1, 12:15] - data[i+2, 12:15]) / (12 * self.delta_t)
            elif i < 2:
                data[i, 6:9] = (8*data[i+1, 3:6] - data[i+2, 3:6]) / (12 * self.delta_t)
                data[i, 15:18] = (8*data[i+1, 12:15] - data[i+2, 12:15]) / (12 * self.delta_t)
        
        return data
    
    def identify_joint_axis(self, calibration_data, max_iter=100):
        """
        Identify joint axis direction using kinematic constraints
        Exploits: ||g1 × j1|| = ||g2 × j2|| for hinge joints
        
        Parameters:
        calibration_data: numpy array from collect_calibration_data
        """
        def cost_function(params):
            """Cost function for joint axis identification"""
            phi1, theta1, phi2, theta2 = params
            
            # Convert spherical to Cartesian
            j1 = np.array([
                np.cos(phi1) * np.cos(theta1),
                np.cos(phi1) * np.sin(theta1),
                np.sin(phi1)
            ])
            j2 = np.array([
                np.cos(phi2) * np.cos(theta2),
                np.cos(phi2) * np.sin(theta2),
                np.sin(phi2)
            ])
            
            # Calculate sum of squared errors
            error = 0.0
            for i in range(len(calibration_data)):
                g1 = calibration_data[i, 3:6]
                g2 = calibration_data[i, 12:15]
                
                cross1 = np.cross(g1, j1)
                cross2 = np.cross(g2, j2)
                
                error += (np.linalg.norm(cross1) - np.linalg.norm(cross2))**2
            
            return error
        
        # Initial guess
        x0 = [0.5, 0.5, 0.5, 0.5]
        
        # Optimize
        result = minimize(cost_function, x0, method='BFGS', 
                         options={'maxiter': max_iter})
        
        phi1, theta1, phi2, theta2 = result.x
        
        # Convert to Cartesian coordinates
        self.j1 = np.array([
            np.cos(phi1) * np.cos(theta1),
            np.cos(phi1) * np.sin(theta1),
            np.sin(phi1)
        ])
        self.j2 = np.array([
            np.cos(phi2) * np.cos(theta2),
            np.cos(phi2) * np.sin(theta2),
            np.sin(phi2)
        ])
        
        # Match signs (ensure they point in same direction)
        self._match_joint_axis_signs(calibration_data)
        
        print(f"Joint axis j1: {self.j1}")
        print(f"Joint axis j2: {self.j2}")
        print(f"Optimization residual: {result.fun:.6f}")
        
    def _match_joint_axis_signs(self, calibration_data):
        """Ensure j1 and j2 point in the same direction"""
        # Find period with minimal angular velocity around joint axis
        min_activity = float('inf')
        min_idx = 0
        
        for i in range(len(calibration_data)):
            g1 = calibration_data[i, 3:6]
            g2 = calibration_data[i, 12:15]
            activity = abs(np.dot(g1, self.j1)) + abs(np.dot(g2, self.j2))
            if activity < min_activity:
                min_activity = activity
                min_idx = i
        
        # Check if projections form mirror images or congruent shapes
        window = 10
        start = max(0, min_idx - window)
        end = min(len(calibration_data), min_idx + window)
        
        proj1_list = []
        proj2_list = []
        
        for i in range(start, end):
            g1 = calibration_data[i, 3:6]
            g2 = calibration_data[i, 12:15]
            
            # Project onto joint plane
            c = np.array([1, 0, 0])
            x1 = np.cross(self.j1, c)
            x1 = x1 / np.linalg.norm(x1) if np.linalg.norm(x1) > 0 else np.array([0, 1, 0])
            y1 = np.cross(self.j1, x1)
            
            x2 = np.cross(self.j2, c)
            x2 = x2 / np.linalg.norm(x2) if np.linalg.norm(x2) > 0 else np.array([0, 1, 0])
            y2 = np.cross(self.j2, x2)
            
            proj1 = np.array([np.dot(g1, x1), np.dot(g1, y1)])
            proj2 = np.array([np.dot(g2, x2), np.dot(g2, y2)])
            
            proj1_list.append(proj1)
            proj2_list.append(proj2)
        
        # Calculate correlation
        proj1_arr = np.array(proj1_list)
        proj2_arr = np.array(proj2_list)
        proj2_neg = -proj2_arr
        
        corr_pos = np.corrcoef(proj1_arr.flatten(), proj2_arr.flatten())[0, 1]
        corr_neg = np.corrcoef(proj1_arr.flatten(), proj2_neg.flatten())[0, 1]
        
        if corr_neg > corr_pos:
            self.j2 = -self.j2
            print("Joint axis signs matched (j2 flipped)")
    
    def identify_joint_position(self, calibration_data, max_iter=100):
        """
        Identify joint position using kinematic constraints
        Exploits: ||a1 - Γ(o1)|| = ||a2 - Γ(o2)|| where Γ is rotational acceleration
        
        Parameters:
        calibration_data: numpy array from collect_calibration_data
        """
        def gamma(g, g_dot, o):
            """Calculate rotational acceleration"""
            return np.cross(g, np.cross(g, o)) + np.cross(g_dot, o)
        
        def cost_function(params):
            """Cost function for joint position identification"""
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
        
        # Initial guess
        x0 = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        
        # Optimize
        result = minimize(cost_function, x0, method='BFGS',
                         options={'maxiter': max_iter})
        
        o1_hat = result.x[0:3]
        o2_hat = result.x[3:6]
        
        # Shift to closest point on joint axis
        shift = (np.dot(o1_hat, self.j1) + np.dot(o2_hat, self.j2)) / 2
        self.o1 = o1_hat - self.j1 * shift
        self.o2 = o2_hat - self.j2 * shift
        
        print(f"Joint position o1: {self.o1}")
        print(f"Joint position o2: {self.o2}")
        print(f"Optimization residual: {result.fun:.6f}")
    
    def calculate_angle(self, imu1_reading, imu2_reading):
        """
        Calculate joint angle from single IMU reading pair
        
        Parameters:
        imu1_reading: dict with Ax, Ay, Az, Gx, Gy, Gz
        imu2_reading: dict with Ax, Ay, Az, Gx, Gy, Gz
        
        Returns:
        float: joint angle in degrees
        """
        if self.j1 is None or self.j2 is None:
            raise ValueError("Joint axes not identified. Run identify_joint_axis first.")
        
        # Extract data
        a1 = np.array([imu1_reading['Ax'], imu1_reading['Ay'], imu1_reading['Az']])
        g1 = np.array([imu1_reading['Gx'], imu1_reading['Gy'], imu1_reading['Gz']])
        a2 = np.array([imu2_reading['Ax'], imu2_reading['Ay'], imu2_reading['Az']])
        g2 = np.array([imu2_reading['Gx'], imu2_reading['Gy'], imu2_reading['Gz']])
        
        # Gyroscope-based angle (incremental)
        angle_gyr_increment = (np.dot(g1, self.j1) - np.dot(g2, self.j2)) * self.delta_t
        angle_gyr = self.prev_angle_gyr + angle_gyr_increment
        
        # Accelerometer-based angle (if position is known)
        if self.o1 is not None and self.o2 is not None:
            # Estimate angular acceleration (simplified - would need g_dot)
            g_dot1 = np.zeros(3)  # Would need history for proper calculation
            g_dot2 = np.zeros(3)
            
            # Shift accelerations to joint center
            gamma1 = np.cross(g1, np.cross(g1, self.o1)) + np.cross(g_dot1, self.o1)
            gamma2 = np.cross(g2, np.cross(g2, self.o2)) + np.cross(g_dot2, self.o2)
            
            a1_shifted = a1 - gamma1
            a2_shifted = a2 - gamma2
            
            # Project onto joint plane
            c = np.array([1, 0, 0])
            x1 = np.cross(self.j1, c)
            x1 = x1 / np.linalg.norm(x1) if np.linalg.norm(x1) > 1e-6 else np.array([0, 1, 0])
            y1 = np.cross(self.j1, x1)
            
            x2 = np.cross(self.j2, c)
            x2 = x2 / np.linalg.norm(x2) if np.linalg.norm(x2) > 1e-6 else np.array([0, 1, 0])
            y2 = np.cross(self.j2, x2)
            
            # Calculate 2D projections
            p1 = np.array([np.dot(a1_shifted, x1), np.dot(a1_shifted, y1)])
            p2 = np.array([np.dot(a2_shifted, x2), np.dot(a2_shifted, y2)])
            
            # Calculate angle between projections
            if np.linalg.norm(p1) > 1e-6 and np.linalg.norm(p2) > 1e-6:
                angle_acc = np.arctan2(p1[1], p1[0]) - np.arctan2(p2[1], p2[0])
                angle_acc = np.degrees(angle_acc)
            else:
                angle_acc = self.prev_angle_acc_gyr
            
            # Complementary filter fusion
            angle = (self.lambda_filter * angle_acc + 
                    (1 - self.lambda_filter) * (self.prev_angle_acc_gyr + angle_gyr - self.prev_angle_gyr))
        else:
            # Only gyroscope available
            angle = angle_gyr
        
        # Update history
        self.prev_angle_gyr = angle_gyr
        self.prev_angle_acc_gyr = angle
        
        return angle


import websocket
import time
from collections import deque

class IMUWebSocketReader:
    def __init__(self, esp_ip, port=81):
        self.esp_ip = esp_ip
        self.port = port
        self.ws = None
        self.is_connected = False
        
    def connect(self):
        """Connect to ESP32 WebSocket"""
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(f"ws://{self.esp_ip}:{self.port}")
            self.is_connected = True
            print(f"✅ Connected to ESP32 at {self.esp_ip}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            self.is_connected = False
            return False
    
    def read_data(self):
        """Read single data packet from WebSocket"""
        if not self.is_connected:
            return None
        try:
            data = self.ws.recv()
            return json.loads(data)
        except Exception as e:
            print(f"❌ Error reading data: {e}")
            self.is_connected = False
            return None
    
    def close(self):
        """Close WebSocket connection"""
        if self.ws:
            self.ws.close()
            self.is_connected = False
            print("🔌 WebSocket connection closed")


def calibration_phase(ws_reader, joint_system, num_samples=50, duration=10):
    """
    Calibration phase: collect data during joint movements
    
    Parameters:
    ws_reader: IMUWebSocketReader instance
    joint_system: IMUJointAngle instance
    num_samples: minimum number of samples to collect
    duration: maximum duration in seconds
    """
    print("\n" + "="*60)
    print("🔧 CALIBRATION PHASE")
    print("="*60)
    print(f"📋 Instructions:")
    print(f"   1. Move the joint in circular motions")
    print(f"   2. Vary the speed and direction")
    print(f"   3. Collecting {num_samples} samples over {duration} seconds")
    print(f"\n⏱️  Starting calibration in 3 seconds...")
    time.sleep(3)
    print("🟢 Calibration started!\n")
    
    imu1_data = []
    imu2_data = []
    start_time = time.time()
    sample_count = 0
    
    try:
        while sample_count < num_samples and (time.time() - start_time) < duration:
            data = ws_reader.read_data()
            if data and 'IMU1' in data and 'IMU2' in data:
                imu1_data.append(data['IMU1'])
                imu2_data.append(data['IMU2'])
                sample_count += 1
                
                # Progress indicator
                if sample_count % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"📊 Collected {sample_count}/{num_samples} samples ({elapsed:.1f}s)")
            
            time.sleep(0.05)  # Small delay between readings
    
    except KeyboardInterrupt:
        print("\n⚠️  Calibration interrupted by user")
    
    print(f"\n✅ Calibration complete! Collected {sample_count} samples")
    
    if sample_count < 20:
        print("⚠️  Warning: Low sample count. Results may be inaccurate.")
        return False
    
    # Process calibration data
    print("\n🔍 Identifying joint axis...")
    calib_data = joint_system.collect_calibration_data(imu1_data, imu2_data)
    joint_system.identify_joint_axis(calib_data)
    
    print("\n🔍 Identifying joint position...")
    joint_system.identify_joint_position(calib_data)
    
    print("\n✅ Calibration successful!")
    return True


def measurement_phase(ws_reader, joint_system, output_file=None):
    """
    Measurement phase: continuous angle calculation
    
    Parameters:
    ws_reader: IMUWebSocketReader instance
    joint_system: IMUJointAngle instance
    output_file: optional filename to save angle data
    """
    print("\n" + "="*60)
    print("📐 MEASUREMENT PHASE")
    print("="*60)
    print("🟢 Real-time joint angle measurement")
    print("   Press Ctrl+C to stop\n")
    
    angles = []
    start_time = time.time()
    measurement_count = 0
    
    # For calculating sampling rate
    last_time = time.time()
    sample_times = deque(maxlen=10)
    
    try:
        while True:
            data = ws_reader.read_data()
            if data and 'IMU1' in data and 'IMU2' in data:
                current_time = time.time()
                elapsed = current_time - start_time
                
                # Calculate angle
                angle = joint_system.calculate_angle(data['IMU1'], data['IMU2'])
                angles.append((elapsed, angle))
                measurement_count += 1
                
                # Calculate actual sampling rate
                sample_times.append(current_time - last_time)
                last_time = current_time
                avg_dt = np.mean(sample_times) if len(sample_times) > 0 else joint_system.delta_t
                
                # Display
                print(f"⏱️  {elapsed:6.2f}s | "
                      f"🔄 Angle: {angle:7.2f}° | "
                      f"📊 Samples: {measurement_count:4d} | "
                      f"⚡ Rate: {1/avg_dt:.1f} Hz", 
                      end='\r')
                
                # Optional: save to file periodically
                if output_file and measurement_count % 100 == 0:
                    with open(output_file, 'a') as f:
                        for t, a in angles[-100:]:
                            f.write(f"{t:.3f},{a:.3f}\n")
            
            time.sleep(0.01)  # Small delay
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Measurement stopped by user")
    
    # Summary statistics
    if angles:
        angle_values = [a for _, a in angles]
        print(f"\n📊 Measurement Summary:")
        print(f"   Duration: {elapsed:.2f} seconds")
        print(f"   Samples: {measurement_count}")
        print(f"   Avg Rate: {measurement_count/elapsed:.1f} Hz")
        print(f"   Angle Range: [{min(angle_values):.2f}°, {max(angle_values):.2f}°]")
        print(f"   Angle Mean: {np.mean(angle_values):.2f}°")
        print(f"   Angle Std: {np.std(angle_values):.2f}°")
    
    return angles


# Main execution
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🦵 IMU-Based Joint Angle Measurement System")
    print("="*60)
    
    # Configuration
    ESP_IP = "10.62.139.36"
    DELTA_T = 0.1  # Expected sampling period (adjust based on your ESP32)
    CALIBRATION_SAMPLES = 50
    CALIBRATION_DURATION = 15  # seconds
    
    # Initialize WebSocket reader
    ws_reader = IMUWebSocketReader(ESP_IP)
    
    if not ws_reader.connect():
        print("❌ Failed to connect. Exiting.")
        exit(1)
    
    # Initialize joint angle system
    joint_system = IMUJointAngle(delta_t=DELTA_T)
    
    try:
        # Phase 1: Calibration
        calibration_success = calibration_phase(
            ws_reader, 
            joint_system, 
            num_samples=CALIBRATION_SAMPLES,
            duration=CALIBRATION_DURATION
        )
        
        if not calibration_success:
            print("❌ Calibration failed. Exiting.")
            ws_reader.close()
            exit(1)
        
        # Phase 2: Measurement
        input("\n⏸️  Press Enter to start measurement phase...")
        angles = measurement_phase(
            ws_reader, 
            joint_system,
            output_file="joint_angles.csv"
        )
        
        # Save final results
        if angles:
            print("\n💾 Saving results to 'joint_angles.csv'...")
            with open("joint_angles.csv", "w") as f:
                f.write("Time(s),Angle(deg)\n")
                for t, a in angles:
                    f.write(f"{t:.3f},{a:.3f}\n")
            print("✅ Results saved!")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        ws_reader.close()
        print("\n👋 Program terminated")
