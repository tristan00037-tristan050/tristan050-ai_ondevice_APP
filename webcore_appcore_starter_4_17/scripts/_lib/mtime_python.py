#!/usr/bin/env python3
"""
✅ S6-S7: mtime 계산 통일 (mac/linux 환경차 제거)
Python으로 mtime을 계산하여 환경 차이를 제거합니다.
"""

import os
import sys
import json
from pathlib import Path

def get_mtime(file_path):
    """파일의 mtime을 Unix timestamp로 반환"""
    try:
        return int(os.path.getmtime(file_path))
    except (OSError, ValueError):
        return 0

def find_latest_mtime(directory, patterns, exclude_dirs=None):
    """
    디렉토리에서 패턴에 맞는 파일들의 최신 mtime을 반환
    
    Args:
        directory: 검색할 디렉토리
        patterns: 파일 패턴 리스트 (예: ['*.ts', '*.tsx'])
        exclude_dirs: 제외할 디렉토리 리스트 (예: ['node_modules', 'docs'])
    
    Returns:
        최신 mtime (Unix timestamp)
    """
    if exclude_dirs is None:
        exclude_dirs = ['node_modules', 'docs', 'fixtures', 'docs/ops', '.git']
    
    latest = 0
    dir_path = Path(directory)
    
    if not dir_path.exists():
        return 0
    
    for root, dirs, files in os.walk(dir_path):
        # exclude_dirs에 포함된 디렉토리는 스킵
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            file_path = Path(root) / file
            # 패턴 매칭
            if any(file_path.match(p) for p in patterns):
                mtime = get_mtime(file_path)
                if mtime > latest:
                    latest = mtime
    
    return latest

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: mtime_python.py <directory> <pattern1> [pattern2] ..."}))
        sys.exit(1)
    
    directory = sys.argv[1]
    patterns = sys.argv[2:]
    
    latest = find_latest_mtime(directory, patterns)
    
    result = {
        "directory": directory,
        "patterns": patterns,
        "latest_mtime": latest
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()

