#!/usr/bin/env python3
"""
Floor Plan Coordinate Mapper
Convert between pixel coordinates (image) and real-world coordinates (meters)
Supports multi-point calibration and affine transformations
"""

import numpy as np
from typing import List, Tuple, Dict, Optional
import json
import math


class FloorPlanMapper:
    """
    Maps pixel coordinates to real-world coordinates using affine transformation.
    Requires minimum 3 calibration points for accurate mapping.
    """
    
    def __init__(self):
        """
        Initialize the floor plan mapper.
        """
        self.calibration_points = []  # List of (pixel_x, pixel_y, real_x, real_y) tuples
        self.transform_matrix = None
        self.inverse_matrix = None
        self.is_calibrated = False
        
    def add_calibration_point(self, pixel_x: float, pixel_y: float, 
                             real_x: float, real_y: float) -> None:
        """
        Add a calibration point mapping pixel coordinates to real-world coordinates.
        
        Args:
            pixel_x, pixel_y: Position in the image (pixels)
            real_x, real_y: Actual position in real-world (meters)
        """
        self.calibration_points.append((pixel_x, pixel_y, real_x, real_y))
        if len(self.calibration_points) >= 3:
            self._compute_transform()
        
    def _compute_transform(self) -> None:
        """
        Compute affine transformation matrix from calibration points.
        Uses least-squares solution for robustness with >3 points.
        """
        if len(self.calibration_points) < 3:
            return
        
        # Extract coordinates
        pixel_coords = np.array([(p[0], p[1]) for p in self.calibration_points])
        real_coords = np.array([(p[2], p[3]) for p in self.calibration_points])
        
        # Build augmented matrix [pixel_x, pixel_y, 1]
        A = np.column_stack([pixel_coords, np.ones(len(pixel_coords))])
        
        # Solve for x and y coefficients separately
        # real_x = a0*pixel_x + a1*pixel_y + a2
        # real_y = b0*pixel_x + b1*pixel_y + b2
        
        try:
            # Use least squares for overdetermined system
            x_coeff, _, _, _ = np.linalg.lstsq(A, real_coords[:, 0], rcond=None)
            y_coeff, _, _, _ = np.linalg.lstsq(A, real_coords[:, 1], rcond=None)
            
            # Store transformation matrix (3x3 homogeneous)
            self.transform_matrix = np.array([
                [x_coeff[0], x_coeff[1], x_coeff[2]],
                [y_coeff[0], y_coeff[1], y_coeff[2]],
                [0, 0, 1]
            ])
            
            # Compute inverse for reverse mapping
            self.inverse_matrix = np.linalg.inv(self.transform_matrix)
            self.is_calibrated = True
            
        except np.linalg.LinAlgError:
            self.is_calibrated = False
            
    def pixel_to_real(self, pixel_x: float, pixel_y: float) -> Optional[Tuple[float, float]]:
        """
        Convert pixel coordinates to real-world coordinates.
        
        Args:
            pixel_x, pixel_y: Position in the image
            
        Returns:
            (real_x, real_y) or None if not calibrated
        """
        if not self.is_calibrated or self.transform_matrix is None:
            return None
        
        # Homogeneous coordinates
        pixel_vec = np.array([pixel_x, pixel_y, 1])
        
        # Apply transformation
        real_vec = self.transform_matrix @ pixel_vec
        
        return float(real_vec[0]), float(real_vec[1])
        
    def real_to_pixel(self, real_x: float, real_y: float) -> Optional[Tuple[float, float]]:
        """
        Convert real-world coordinates to pixel coordinates (reverse mapping).
        
        Args:
            real_x, real_y: Real-world position
            
        Returns:
            (pixel_x, pixel_y) or None if not calibrated
        """
        if not self.is_calibrated or self.inverse_matrix is None:
            return None
        
        # Homogeneous coordinates
        real_vec = np.array([real_x, real_y, 1])
        
        # Apply inverse transformation
        pixel_vec = self.inverse_matrix @ real_vec
        
        return float(pixel_vec[0]), float(pixel_vec[1])
        
    def calculate_calibration_error(self) -> Optional[float]:
        """
        Calculate RMS error of calibration (in meters).
        Tests the transformation on all calibration points.
        
        Returns:
            RMS error or None if not calibrated
        """
        if not self.is_calibrated:
            return None
        
        errors = []
        for pixel_x, pixel_y, real_x, real_y in self.calibration_points:
            mapped = self.pixel_to_real(pixel_x, pixel_y)
            if mapped:
                dx = mapped[0] - real_x
                dy = mapped[1] - real_y
                error = math.sqrt(dx**2 + dy**2)
                errors.append(error)
        
        if not errors:
            return None
        
        return math.sqrt(sum(e**2 for e in errors) / len(errors))
        
    def get_calibration_points(self) -> List[Dict]:
        """
        Get all calibration points as dictionaries.
        """
        return [
            {
                'pixel_x': p[0],
                'pixel_y': p[1],
                'real_x': p[2],
                'real_y': p[3]
            }
            for p in self.calibration_points
        ]
        
    def save_calibration(self, filepath: str) -> bool:
        """
        Save calibration data to JSON file.
        """
        try:
            data = {
                'calibration_points': self.get_calibration_points(),
                'is_calibrated': self.is_calibrated,
                'calibration_error': self.calculate_calibration_error()
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving calibration: {e}")
            return False
            
    def load_calibration(self, filepath: str) -> bool:
        """
        Load calibration data from JSON file.
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.calibration_points = []
            for point in data['calibration_points']:
                self.add_calibration_point(
                    point['pixel_x'],
                    point['pixel_y'],
                    point['real_x'],
                    point['real_y']
                )
            return True
        except Exception as e:
            print(f"Error loading calibration: {e}")
            return False
            
    def get_scale_factors(self) -> Optional[Tuple[float, float]]:
        """
        Estimate scale factors (pixels per meter) in X and Y directions.
        
        Returns:
            (pixels_per_meter_x, pixels_per_meter_y) or None
        """
        if len(self.calibration_points) < 2:
            return None
        
        # Find two points with maximum distance
        max_dist_pixel = 0
        max_dist_real = 0
        point_pair = None
        
        for i in range(len(self.calibration_points)):
            for j in range(i + 1, len(self.calibration_points)):
                p1 = self.calibration_points[i]
                p2 = self.calibration_points[j]
                
                pixel_dist = math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
                real_dist = math.sqrt((p1[2] - p2[2])**2 + (p1[3] - p2[3])**2)
                
                if real_dist > max_dist_real:
                    max_dist_pixel = pixel_dist
                    max_dist_real = real_dist
                    point_pair = (i, j)
        
        if max_dist_real > 0:
            scale = max_dist_pixel / max_dist_real
            return (scale, scale)
        
        return None


def create_simple_transform(image_width: float, image_height: float,
                          real_width: float, real_height: float) -> FloorPlanMapper:
    """
    Create a simple mapper assuming the image directly represents real-world coordinates.
    Useful for quick setup without manual calibration.
    
    Args:
        image_width, image_height: Image dimensions in pixels
        real_width, real_height: Real-world dimensions in meters
        
    Returns:
        Configured FloorPlanMapper
    """
    mapper = FloorPlanMapper()
    
    # Use corners as calibration points
    mapper.add_calibration_point(0, 0, 0, 0)
    mapper.add_calibration_point(image_width, 0, real_width, 0)
    mapper.add_calibration_point(0, image_height, 0, real_height)
    
    return mapper
