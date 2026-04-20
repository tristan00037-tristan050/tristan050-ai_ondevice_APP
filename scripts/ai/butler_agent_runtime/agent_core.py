from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .audit_logger import AuditLogger
from .egress_block import verify_no_egress
from .model_loader import apply_fallback, load, probe_device, select_model
from .privacy_guard import scan
from .runtime_contracts import AgentResponse, PolicyConfig, RuntimeReport
from .session_manager import SessionManager
from .task_router import classify_task


def _digest16(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


class ButlerAgent:
    def __init__(self, audit_path: str | Path = 'tmp/agent_runtime_audit.jsonl'):
        self.audit = AuditLogger(audit_path)
        self.sessions = SessionManager()

    def _prepare_inputs(self, tokenizer, prompt: str):
        messages = [{'role': 'user', 'content': prompt}]
        return tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            return_tensors='pt',
            add_generation_prompt=True,
        )

    def _real_output(self, model, tokenizer, prompt: str) -> str:
        import torch
        inputs = self._prepare_inputs(tokenizer, prompt)
        if hasattr(inputs, 'to') and hasattr(model, 'device'):
            try:
                inputs = inputs.to(model.device)
            except Exception:
                pass
        with torch.no_grad():
            out = model.generate(inputs, max_new_tokens=128, temperature=0.0, do_sample=False)
        output = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()
        return output

    def run(
        self,
        text: str,
        high_model_path: str,
        light_model_path: str,
        adapter_path: str,
        force: str | None = None,
        policy: PolicyConfig | None = None,
        dev_fallback: bool = False,
        require_real_backend: bool = False,
    ) -> tuple[AgentResponse, dict]:
        policy = policy or PolicyConfig(policy_id='default')
        session = self.sessions.create_session('demo_user', 'demo_device', policy.policy_id, 'pending', 'pending')
        scan_in = scan(text)
        decision = classify_task(scan_in.masked_text, policy)
        profile = probe_device()
        router = select_model(profile, force=force)
        session.selected_model = router['selected']
        session.route_reason = router['reason_code']
        self.sessions.append_turn(session.session_id, 'user', text, task=decision.task, selected_model=router['selected'])
        target_model_path = high_model_path if router['selected'] == 'high' else light_model_path
        target_adapter = adapter_path if router['selected'] == 'high' else None
        model, tokenizer, meta = load(target_model_path, target_adapter, selected=router['selected'], dev_fallback=dev_fallback)
        if router['selected'] == 'high' and (model is None or tokenizer is None or meta.backend == 'local_echo'):
            router = apply_fallback(router, 'high_model_load_failed')
            model, tokenizer, meta = load(light_model_path, None, selected='light', dev_fallback=dev_fallback)
            meta.fallback_used = 1
            meta.fallback_reason = router.get('fallback_reason', 'high_model_load_failed')
            meta.primary_selected = 'high'
            meta.selected = 'light'
        if require_real_backend and meta.backend != 'transformers':
            raise RuntimeError('real_backend_required')
        output = self._real_output(model, tokenizer, scan_in.masked_text)
        scan_out = scan(output)
        egress_ok, egress_code = verify_no_egress()
        self.sessions.append_turn(session.session_id, 'assistant', output, task=decision.task, selected_model=router['selected'])
        self.audit.log(
            session_id=session.session_id,
            device_id=session.device_id,
            selected_model=router['selected'],
            route_reason=router['reason_code'],
            policy_id=policy.policy_id,
            event_code='agent_run',
            input_digest16=scan_in.digest16,
            output_digest16=scan_out.digest16,
            blocked=not egress_ok,
            backend=meta.backend,
            fallback_used=router.get('fallback_used', 0),
            fallback_reason=router.get('fallback_reason', ''),
            sensitive_hit_types=scan_in.hit_types + scan_out.hit_types,
            error_code='' if egress_ok else egress_code,
            message='ok' if egress_ok else egress_code,
        )
        resp = AgentResponse(
            ok=bool(egress_ok),
            task=decision.task,
            selected_model=router['selected'],
            response_digest16=scan_out.digest16,
            response_len=len(output),
            policy_code='ok',
            fallback_used=int(router.get('fallback_used', 0)),
            route_reason=router['reason_code'],
            blocked=not egress_ok,
            sensitive_hit_types=scan_in.hit_types + scan_out.hit_types,
        )
        return resp, {'profile': profile.to_dict(), 'router': router, 'load_meta': meta.to_dict()}


def build_runtime_report(resp: AgentResponse, meta: dict, out_path: str | Path = 'tmp/agent_runtime_report.json', execution_mode: str = 'local_e2e', audit_path: str = 'tmp/agent_runtime_audit.jsonl') -> None:
    load_meta = meta['load_meta']
    payload = RuntimeReport(
        schema_version='3.0',
        generated_at=datetime.now(timezone.utc).isoformat(),
        execution_mode=execution_mode,
        effective_backend=load_meta.get('backend', ''),
        quant_mode=load_meta.get('quant_mode', ''),
        fallback_used=int(load_meta.get('fallback_used', 0)),
        fallback_reason=load_meta.get('fallback_reason', ''),
        product_ready=1 if load_meta.get('backend') == 'transformers' and not resp.blocked else 0,
        selected_model=resp.selected_model,
        route_reason=resp.route_reason,
        audit_path=str(audit_path),
        response_digest16=resp.response_digest16,
        checks={'response_ok': int(resp.ok), 'egress_ok': int(not resp.blocked)},
        fail_codes=[] if resp.ok else ['egress_block_failed'],
    ).to_dict()
    payload['device_profile'] = meta['profile']
    payload['router_result'] = meta['router']
    payload['response_meta'] = resp.to_dict()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--offline-demo', action='store_true')
    ap.add_argument('--require-real-backend', action='store_true')
    ap.add_argument('--dev-fallback', action='store_true')
    ap.add_argument('--high-model-path', default='Qwen/Qwen3-4B')
    ap.add_argument('--light-model-path', default='Qwen/Qwen3-1.5B')
    ap.add_argument('--adapter-path', default='/data/butler_output/')
    ap.add_argument('--json-out', default='tmp/agent_runtime_report.json')
    args = ap.parse_args(argv)

    agent = ButlerAgent()
    text = '다음 고객 문의를 요약하고 연락처 010-1234-5678은 마스킹해 주세요.'
    resp, meta = agent.run(
        text,
        args.high_model_path,
        args.light_model_path,
        args.adapter_path,
        dev_fallback=args.dev_fallback or args.offline_demo,
        require_real_backend=args.require_real_backend,
    )
    build_runtime_report(resp, meta, args.json_out, execution_mode='local_e2e' if args.offline_demo else 'real_local')
    print(f'AGENT_RUNTIME_OK={1 if resp.ok else 0}')
    print(f'AGENT_RUNTIME_MODEL={resp.selected_model}')
    print(f'AGENT_RUNTIME_BACKEND={meta["load_meta"].get("backend", "")}')
    print(f'AGENT_RUNTIME_FALLBACK_USED={int(meta["router"].get("fallback_used", 0))}')
    print(f'AGENT_RUNTIME_REPORT={args.json_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
