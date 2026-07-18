#!/usr/bin/env python3
"""
UWB Serial Data Reader
Reads real-time range measurements from UWB hardware (DWM1001) via UART/Serial
"""

import serial
import json
import re
from datetime import datetime
from typing import Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class UWBSerialReader:
    """
    Reads UWB range measurements from serial port.
    Parses JSON or line-delimited format from DWM1001 devices.
    """
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: int = 1):
        """
        Initialize serial connection.
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0', 'COM3')
            baudrate: Baud rate (default 115200 for DWM1001)
            timeout: Serial read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.callback = None
        
    def connect(self) -> bool:
        """
        Open serial connection.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
            
    def disconnect(self) -> None:
        """
        Close serial connection.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Serial connection closed")
            
    def set_callback(self, callback: Callable[[Dict], None]) -> None:
        """
        Set callback function to be called when ranges are received.
        
        Args:
            callback: Function that accepts dict with range data
        """
        self.callback = callback
        
    def read_line(self) -> Optional[str]:
        """
        Read one line from serial.
        
        Returns:
            Line string or None if timeout/error
        """
        if not self.ser:
            return None
            
        try:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8').strip()
                return line
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            
        return None
        
    def parse_json_ranges(self, line: str) -> Optional[Dict[str, float]]:
        """
        Parse JSON-formatted range data.
        Expected format: {"anchor_0": 2.5, "anchor_1": 3.2, ...}
        
        Args:
            line: JSON string
            
        Returns:
            Dict of anchor_id -> distance or None if parse fails
        """
        try:
            data = json.loads(line)
            # Filter to only numeric values (distances)
            ranges = {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
            return ranges if ranges else None
        except (json.JSONDecodeError, ValueError):
            return None
            
    def parse_csv_ranges(self, line: str) -> Optional[Dict[str, float]]:
        """
        Parse CSV-formatted range data.
        Expected format: anchor_0,2.5,anchor_1,3.2,...
        
        Args:
            line: CSV string
            
        Returns:
            Dict of anchor_id -> distance or None
        """
        try:
            parts = line.split(',')
            ranges = {}
            for i in range(0, len(parts) - 1, 2):
                anchor_id = parts[i].strip()
                distance = float(parts[i + 1].strip())
                ranges[anchor_id] = distance
            return ranges if ranges else None
        except (ValueError, IndexError):
            return None
            
    def parse_dwm1001_format(self, line: str) -> Optional[Dict[str, float]]:
        """
        Parse DWM1001 proprietary format.
        Example: "POS:x=1.2,y=3.4 RANGES:a0=2.1,a1=3.2,a2=2.9,a3=4.1"
        
        Args:
            line: DWM1001 format string
            
        Returns:
            Dict of anchor_id -> distance
        """
        ranges = {}
        
        # Extract ranges section
        ranges_match = re.search(r'RANGES:([^\s]+)', line)
        if not ranges_match:
            return None
            
        ranges_str = ranges_match.group(1)
        pairs = ranges_str.split(',')
        
        for pair in pairs:
            try:
                anchor_id, distance = pair.split('=')
                ranges[anchor_id.strip()] = float(distance.strip())
            except ValueError:
                continue
                
        return ranges if ranges else None
        
    def read_ranges(self, format_type: str = 'auto') -> Optional[Dict[str, float]]:
        """
        Read and parse range data from serial.
        
        Args:
            format_type: 'json', 'csv', 'dwm1001', or 'auto'
            
        Returns:
            Dict of anchor_id -> distance or None
        """
        line = self.read_line()
        if not line:
            return None
            
        # Try to parse based on format
        if format_type == 'json' or format_type == 'auto':
            ranges = self.parse_json_ranges(line)
            if ranges:
                return ranges
                
        if format_type == 'csv' or format_type == 'auto':
            ranges = self.parse_csv_ranges(line)
            if ranges:
                return ranges
                
        if format_type == 'dwm1001' or format_type == 'auto':
            ranges = self.parse_dwm1001_format(line)
            if ranges:
                return ranges
                
        logger.warning(f"Could not parse line: {line}")
        return None
        
    def run(self, format_type: str = 'auto') -> None:
        """
        Continuously read and process range data.
        Calls callback for each reading.
        
        Args:
            format_type: Format type for parsing
        """
        if not self.connect():
            return
            
        try:
            logger.info("Starting to read UWB ranges...")
            while True:
                ranges = self.read_ranges(format_type)
                if ranges and self.callback:
                    self.callback(ranges)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.disconnect()


def create_mock_reader():
    """
    Create a mock reader for testing (generates synthetic data).
    """
    class MockUWBReader:
        def __init__(self):
            self.callback = None
            
        def set_callback(self, callback):
            self.callback = callback
            
        def run(self, format_type='auto'):
            import time
            import random
            logger.info("Mock reader: generating synthetic UWB data...")
            while True:
                ranges = {
                    'anchor_0': 2.5 + random.gauss(0, 0.1),
                    'anchor_1': 3.2 + random.gauss(0, 0.1),
                    'anchor_2': 2.9 + random.gauss(0, 0.1),
                    'anchor_3': 4.1 + random.gauss(0, 0.1),
                }
                if self.callback:
                    self.callback(ranges)
                time.sleep(0.1)
                
    return MockUWBReader()
