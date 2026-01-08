#!/usr/bin/env python3
"""
Policy Diff Risk Score Calculator (Policy-as-Code v1)
정책 파일 diff를 파싱하여 Risk Score 산출 (meta-only)
"""

import sys
import json
import re
from typing import Dict, List, Set, Tuple, Optional

# Risk Score 가중치 (허용 범위 확대/검사 약화 감지)
RISK_WEIGHTS = {
    'forbidden_field_removed': 10,  # 금지 필드 제거
    'required_header_removed': 10,  # 필수 헤더 제거
    'max_limit_days_increased': 5,  # max_limit_days 증가
    'allowed_field_added': 5,  # allowed_fields 추가
    'action_block_to_allow': 20,  # action: block -> allow
    'rule_removed': 15,  # 규칙 전체 제거
    'forbidden_field_added': -5,  # 금지 필드 추가 (강화)
    'required_header_added': -5,  # 필수 헤더 추가 (강화)
    'max_limit_days_decreased': -5,  # max_limit_days 감소 (강화)
}

# Risk Flag 코드
RISK_FLAGS = {
    'forbidden_field_removed': 'FORBIDDEN_FIELD_REMOVED',
    'required_header_removed': 'REQUIRED_HEADER_REMOVED',
    'max_limit_days_increased': 'MAX_LIMIT_DAYS_INCREASED',
    'allowed_field_added': 'ALLOWED_FIELD_ADDED',
    'action_block_to_allow': 'ACTION_BLOCK_TO_ALLOW',
    'rule_removed': 'RULE_REMOVED',
    'forbidden_field_added': 'FORBIDDEN_FIELD_ADDED',
    'required_header_added': 'REQUIRED_HEADER_ADDED',
    'max_limit_days_decreased': 'MAX_LIMIT_DAYS_DECREASED',
}


def parse_yaml_simple(content: str) -> Dict:
    """간단한 YAML 파싱 (정책 파일 구조만 지원)"""
    policy = {'version': '', 'rules': []}
    lines = content.split('\n')
    current_rule = None
    in_rules = False
    current_key = ''
    current_array = []
    rule_indent = -1
    
    for line in lines:
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('#'):
            continue
        
        indent = len(line) - len(line.lstrip())
        
        if trimmed.startswith('version:'):
            policy['version'] = trimmed.split(':', 1)[1].strip().strip('"\'')
        elif trimmed == 'rules:':
            in_rules = True
            rule_indent = indent
        elif in_rules and indent > rule_indent:
            if trimmed.startswith('- id:'):
                if current_rule:
                    if current_array and current_key:
                        current_rule[current_key] = current_array
                        current_array = []
                    policy['rules'].append(current_rule)
                current_rule = {
                    'id': trimmed.split(':', 1)[1].strip().strip('"\''),
                    'name': '',
                    'description': '',
                    'action': 'block',
                }
                current_key = ''
            elif current_rule:
                if ':' in trimmed:
                    if current_array and current_key:
                        current_rule[current_key] = current_array
                        current_array = []
                    key, value = trimmed.split(':', 1)
                    current_key = key.strip()
                    value = value.strip().strip('"\'')
                    if current_key in ('name', 'description', 'action'):
                        current_rule[current_key] = value
                    elif current_key == 'max_limit_days':
                        current_rule[current_key] = int(value) if value.isdigit() else 0
                elif trimmed.startswith('- '):
                    item = trimmed[2:].strip().strip('"\'')
                    if item:
                        current_array.append(item)
    
    if current_rule:
        if current_array and current_key:
            current_rule[current_key] = current_array
        policy['rules'].append(current_rule)
    
    return policy


def find_rule_by_id(rules: List[Dict], rule_id: str) -> Optional[Dict]:
    """rule_id로 규칙 찾기"""
    for rule in rules:
        if rule.get('id') == rule_id:
            return rule
    return None


def compare_rules(old_rule: Dict, new_rule: Dict) -> Tuple[int, List[str]]:
    """두 규칙 비교하여 Risk Score와 Flags 반환"""
    score = 0
    flags = []
    
    # action 변경: block -> allow
    old_action = old_rule.get('action', 'block')
    new_action = new_rule.get('action', 'block')
    if old_action == 'block' and new_action == 'allow':
        score += RISK_WEIGHTS['action_block_to_allow']
        flags.append(RISK_FLAGS['action_block_to_allow'])
    
    # forbidden_fields 비교
    old_forbidden = set(old_rule.get('forbidden_fields', []))
    new_forbidden = set(new_rule.get('forbidden_fields', []))
    removed = old_forbidden - new_forbidden
    added = new_forbidden - old_forbidden
    if removed:
        score += RISK_WEIGHTS['forbidden_field_removed'] * len(removed)
        flags.append(f"{RISK_FLAGS['forbidden_field_removed']}:{len(removed)}")
    if added:
        score += RISK_WEIGHTS['forbidden_field_added'] * len(added)
        flags.append(f"{RISK_FLAGS['forbidden_field_added']}:{len(added)}")
    
    # required_headers 비교
    old_required = set(old_rule.get('required_headers', []))
    new_required = set(new_rule.get('required_headers', []))
    removed = old_required - new_required
    added = new_required - old_required
    if removed:
        score += RISK_WEIGHTS['required_header_removed'] * len(removed)
        flags.append(f"{RISK_FLAGS['required_header_removed']}:{len(removed)}")
    if added:
        score += RISK_WEIGHTS['required_header_added'] * len(added)
        flags.append(f"{RISK_FLAGS['required_header_added']}:{len(added)}")
    
    # max_limit_days 비교
    old_limit = old_rule.get('max_limit_days')
    new_limit = new_rule.get('max_limit_days')
    if old_limit is not None and new_limit is not None:
        if new_limit > old_limit:
            score += RISK_WEIGHTS['max_limit_days_increased']
            flags.append(RISK_FLAGS['max_limit_days_increased'])
        elif new_limit < old_limit:
            score += RISK_WEIGHTS['max_limit_days_decreased']
            flags.append(RISK_FLAGS['max_limit_days_decreased'])
    
    # allowed_fields 비교
    old_allowed = set(old_rule.get('allowed_fields', []))
    new_allowed = set(new_rule.get('allowed_fields', []))
    added = new_allowed - old_allowed
    if added:
        score += RISK_WEIGHTS['allowed_field_added'] * len(added)
        flags.append(f"{RISK_FLAGS['allowed_field_added']}:{len(added)}")
    
    return score, flags


def calculate_risk_score(old_content: str, new_content: str) -> Tuple[int, List[str]]:
    """정책 파일 diff로부터 Risk Score 계산"""
    old_policy = parse_yaml_simple(old_content)
    new_policy = parse_yaml_simple(new_content)
    
    total_score = 0
    all_flags = []
    
    old_rules = {r['id']: r for r in old_policy.get('rules', [])}
    new_rules = {r['id']: r for r in new_policy.get('rules', [])}
    
    # 기존 규칙 변경/제거
    for rule_id, old_rule in old_rules.items():
        if rule_id not in new_rules:
            # 규칙 제거
            total_score += RISK_WEIGHTS['rule_removed']
            all_flags.append(f"{RISK_FLAGS['rule_removed']}:{rule_id}")
        else:
            # 규칙 변경
            score, flags = compare_rules(old_rule, new_rules[rule_id])
            total_score += score
            all_flags.extend(flags)
    
    # 새 규칙 추가는 중립 (점수 없음)
    
    # 음수 점수는 0으로 클램핑
    total_score = max(0, total_score)
    
    return total_score, all_flags


def main():
    if len(sys.argv) < 3:
        print("Usage: calc_policy_diff_risk.py <old_file> <new_file>", file=sys.stderr)
        sys.exit(2)
    
    old_file = sys.argv[1]
    new_file = sys.argv[2]
    
    try:
        with open(old_file, 'r', encoding='utf-8') as f:
            old_content = f.read()
        with open(new_file, 'r', encoding='utf-8') as f:
            new_content = f.read()
    except FileNotFoundError as e:
        print(f"FAIL: file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: error reading files: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        risk_score, risk_flags = calculate_risk_score(old_content, new_content)
    except Exception as e:
        print(f"FAIL: error calculating risk: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Meta-only 출력 (본문 0)
    output = {
        'RISK_SCORE': risk_score,
        'RISK_FLAGS': risk_flags,
        'RISK_FLAG_COUNT': len(risk_flags),
    }
    
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    sys.exit(0)


if __name__ == '__main__':
    main()

