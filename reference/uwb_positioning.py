#!/usr/bin/env python3
"""
UWB Indoor Positioning Module
Implements trilateration algorithm for position estimation from UWB range measurements
"""

import math
import numpy as np
from collections import deque
from typing import List, Tuple, Dict, Optional


class UWBPositioning:
    """
    UWB-based indoor positioning system using trilateration.
    Estimates 2D/3D position from distances to known anchor points.
    """

    def __init__(self, num_anchors: int = 4, history_size: int = 10):
        """
        Initialize UWB positioning system.
        
        Args:
            num_anchors: Number of fixed UWB anchors (minimum 3 for 2D, 4 for 3D)
            history_size: Number of historical positions to maintain
        """
        self.num_anchors = num_anchors
        self.anchors = {}  # Dict of anchor_id -> (x, y, z) coordinates
        self.history = deque(maxlen=history_size)
        self.kalman_filter = KalmanFilter1D()
        
    def add_anchor(self, anchor_id: str, x: float, y: float, z: float = 0.0) -> None:
        """
        Register a UWB anchor at known coordinates.
        
        Args:
            anchor_id: Unique identifier for the anchor
            x, y, z: 3D coordinates of the anchor
        """
        self.anchors[anchor_id] = (x, y, z)
        
    def trilaterate_2d(self, ranges: Dict[str, float]) -> Optional[Tuple[float, float]]:
        """
        Estimate 2D position using trilateration.
        Requires at least 3 anchors with valid range measurements.
        
        Args:
            ranges: Dict mapping anchor_id -> distance (in meters)
            
        Returns:
            (x, y) coordinates or None if insufficient data
        """
        valid_ranges = {aid: dist for aid, dist in ranges.items() if aid in self.anchors}
        
        if len(valid_ranges) < 3:
            return None
            
        # Extract anchor coordinates and distances
        anchors_list = []
        distances_list = []
        
        for anchor_id, distance in valid_ranges.items():
            x, y, z = self.anchors[anchor_id]
            anchors_list.append((x, y))
            distances_list.append(distance)
            
        # Least squares trilateration
        return self._least_squares_trilateration_2d(anchors_list, distances_list)
        
    def trilaterate_3d(self, ranges: Dict[str, float]) -> Optional[Tuple[float, float, float]]:
        """
        Estimate 3D position using trilateration.
        Requires at least 4 anchors with valid range measurements.
        
        Args:
            ranges: Dict mapping anchor_id -> distance (in meters)
            
        Returns:
            (x, y, z) coordinates or None if insufficient data
        """
        valid_ranges = {aid: dist for aid, dist in ranges.items() if aid in self.anchors}
        
        if len(valid_ranges) < 4:
            return None
            
        anchors_list = []
        distances_list = []
        
        for anchor_id, distance in valid_ranges.items():
            anchor_pos = self.anchors[anchor_id]
            anchors_list.append(anchor_pos)
            distances_list.append(distance)
            
        return self._least_squares_trilateration_3d(anchors_list, distances_list)
        
    def _least_squares_trilateration_2d(self, anchors: List[Tuple[float, float]], 
                                       distances: List[float]) -> Tuple[float, float]:
        """
        Least squares solution for 2D trilateration.
        Minimizes sum of squared errors.
        """
        num_anchors = len(anchors)
        
        # Build the matrix equation: A*x = b
        A = np.zeros((num_anchors - 1, 2))
        b = np.zeros(num_anchors - 1)
        
        x0, y0 = anchors[0]
        r0 = distances[0]
        
        for i in range(1, num_anchors):
            xi, yi = anchors[i]
            ri = distances[i]
            
            A[i-1, 0] = 2 * (xi - x0)
            A[i-1, 1] = 2 * (yi - y0)
            b[i-1] = (ri**2 - r0**2) - (xi**2 - x0**2) - (yi**2 - y0**2)
            
        # Solve using least squares
        try:
            pos, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            return float(pos[0]), float(pos[1])
        except:
            return None
            
    def _least_squares_trilateration_3d(self, anchors: List[Tuple[float, float, float]], 
                                       distances: List[float]) -> Tuple[float, float, float]:
        """
        Least squares solution for 3D trilateration.
        """
        num_anchors = len(anchors)
        
        A = np.zeros((num_anchors - 1, 3))
        b = np.zeros(num_anchors - 1)
        
        x0, y0, z0 = anchors[0]
        r0 = distances[0]
        
        for i in range(1, num_anchors):
            xi, yi, zi = anchors[i]
            ri = distances[i]
            
            A[i-1, 0] = 2 * (xi - x0)
            A[i-1, 1] = 2 * (yi - y0)
            A[i-1, 2] = 2 * (zi - z0)
            b[i-1] = (ri**2 - r0**2) - (xi**2 - x0**2) - (yi**2 - y0**2) - (zi**2 - z0**2)
            
        try:
            pos, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            return float(pos[0]), float(pos[1]), float(pos[2])
        except:
            return None
            
    def smooth_position(self, position: Tuple[float, float], 
                       smoothing_factor: float = 0.7) -> Tuple[float, float]:
        """
        Apply Kalman filtering to smooth position estimates.
        Reduces noise from UWB measurements.
        
        Args:
            position: Current (x, y) measurement
            smoothing_factor: Higher = more smoothing (0-1)
            
        Returns:
            Smoothed (x, y) position
        """
        if not self.history:
            self.history.append(position)
            return position
            
        last_x, last_y = self.history[-1]
        curr_x, curr_y = position
        
        # Simple exponential smoothing
        smooth_x = smoothing_factor * last_x + (1 - smoothing_factor) * curr_x
        smooth_y = smoothing_factor * last_y + (1 - smoothing_factor) * curr_y
        
        smoothed = (smooth_x, smooth_y)
        self.history.append(smoothed)
        
        return smoothed
        
    def calculate_accuracy(self, position: Tuple[float, float], 
                          ranges: Dict[str, float]) -> float:
        """
        Estimate positioning accuracy using RMSE.
        
        Args:
            position: Estimated (x, y) position
            ranges: Measured distances to anchors
            
        Returns:
            Root Mean Squared Error in meters
        """
        x, y = position
        squared_errors = []
        
        for anchor_id, measured_dist in ranges.items():
            if anchor_id not in self.anchors:
                continue
                
            ax, ay, _ = self.anchors[anchor_id]
            expected_dist = math.sqrt((x - ax)**2 + (y - ay)**2)
            error = measured_dist - expected_dist
            squared_errors.append(error**2)
            
        if not squared_errors:
            return 0.0
            
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors))
        return rmse


class KalmanFilter1D:
    """
    1D Kalman Filter for smoothing individual coordinate measurements.
    """
    
    def __init__(self, process_variance: float = 0.01, 
                 measurement_variance: float = 0.1, 
                 initial_value: float = 0.0):
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.estimate = initial_value
        self.estimate_error = 1.0
        
    def update(self, measurement: float) -> float:
        """
        Update filter with new measurement.
        """
        # Predict
        prediction = self.estimate
        prediction_error = self.estimate_error + self.process_variance
        
        # Update
        kalman_gain = prediction_error / (prediction_error + self.measurement_variance)
        self.estimate = prediction + kalman_gain * (measurement - prediction)
        self.estimate_error = (1 - kalman_gain) * prediction_error
        
        return self.estimate


def simulate_uwb_ranges(tag_position: Tuple[float, float], 
                       anchors: Dict[str, Tuple[float, float, float]], 
                       noise_std: float = 0.1) -> Dict[str, float]:
    """
    Simulate UWB range measurements (for testing).
    Adds Gaussian noise to distances.
    
    Args:
        tag_position: True (x, y) position of tag
        anchors: Dict of anchor_id -> (x, y, z) coordinates
        noise_std: Standard deviation of Gaussian noise in meters
        
    Returns:
        Dict of anchor_id -> measured distance
    """
    ranges = {}
    tag_x, tag_y = tag_position
    
    for anchor_id, (ax, ay, az) in anchors.items():
        true_distance = math.sqrt((tag_x - ax)**2 + (tag_y - ay)**2)
        noise = np.random.normal(0, noise_std)
        measured_distance = true_distance + noise
        ranges[anchor_id] = max(0.0, measured_distance)  # Distance cannot be negative
        
    return ranges
