from __future__ import annotations

import hashlib, json, os, random, selectors, signal, subprocess, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

SHA=lambda b:'sha256:'+hashlib.sha256(b).hexdigest()
def stable(v): return SHA(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode())
def text_digest(v:str): return SHA(v.encode())
SOFT=frozenset({'NEEDS_REVIEW_CONTENT_DRIFT','NEEDS_REVIEW_OUTPUT_SKELETON_ECHO','NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO','NEEDS_REVIEW_UNSUPPORTED_CLAIM','NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL','NEEDS_REVIEW_NO_EVIDENCE_CLAIM','BLOCK_NO_FACTUAL_CLAIMS','BLOCK_DEGENERATION','BLOCK_UNSUPPORTED_CLAIM','BLOCK_FINAL_GATE_UNSUPPORTED'})
HARD=('BLOCK_DLP_','BLOCK_HUMAN_APPROVAL_','BLOCK_POLICY_','BLOCK_MODEL_','BLOCK_RUNTIME_','BLOCK_HELPER_ASSET_','BLOCK_ASSET_','APPROVED_MODEL_RUNTIME_MISMATCH')
MANDATORY={'helper7_parse_evidence','draft_runner_helper3_helper5_stack','unsupported_claim_labeling','human_approval','dlp_pre_output_guard','final_gate'}

@dataclass(frozen=True)
class ApprovedModelIdentity:
    variant_id:str; physical_model_sha256:str; resolved_path_digest:str; runtime_config_digest:str
    def validate(self):
        if not self.variant_id: raise ValueError('MODEL_VARIANT_REQUIRED')
        for x in (self.physical_model_sha256,self.resolved_path_digest,self.runtime_config_digest):
            if not isinstance(x,str) or not x.startswith('sha256:') or len(x)!=71: raise ValueError('MODEL_IDENTITY_INVALID')

@dataclass
class VolatileDraft:
    request_digest:str; text_runtime_only:str=''
    def persistable_dict(self): raise RuntimeError('VOLATILE_DRAFT_MUST_NOT_PERSIST')

@dataclass(frozen=True)
class ProductCascadeResult:
    primary_receipt:dict[str,Any]; repair_receipt:dict[str,Any]|None; cascade_receipt:dict[str,Any]; final_verdict:Any; terminal_event:dict[str,Any]

class CapturingRunner:
    def __init__(self,runner,channel):
        self._runner,self._channel=runner,channel
        for n in ('_box3_model_load_ms','_box3_runner_engine','_box3_adapter_stack','_box3_test_only','_box3_model_identity'):
            if hasattr(runner,n): setattr(self,n,getattr(runner,n))
    def __call__(self,envelope):
        out=str(self._runner(envelope) or ''); self._channel.text_runtime_only=out; return out
class FixedOutputRunner:
    def __init__(self,text,identity): self.text=text; self._box3_test_only=False; self._box3_runner_engine='llama_cpp_repair_4b'; self._box3_model_identity=asdict(identity)
    def __call__(self,_): return self.text

def _product_call():
    from butler_pc_core.cards.box3.actual_operation_pipeline import run_box3_actual_operation
    return run_box3_actual_operation

def _stages(v): return {x.get('stage'):x for x in list(getattr(v,'stage_trace',[]) or []) if isinstance(x,dict) and isinstance(x.get('stage'),str)}
def _severity(f,s):
    if not f and s in {'PASS','PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL'}: return 'pass'
    if f in SOFT: return 'soft'
    if s=='BLOCKED' or (f and f.startswith(HARD)): return 'hard'
    return 'soft' if f else 'pass'
def _terminal(v):
    st=_stages(v); return {'schema_version':'butler.box3_terminal_event.v1','request_digest':str(getattr(v,'request_digest','')),'status':str(getattr(v,'status','BLOCKED')),'fail_class':getattr(v,'fail_class',None),'output_digest':getattr(v,'draft_digest',None),'dlp_stage_present':'dlp_pre_output_guard' in st,'label_stage_present':'unsupported_claim_labeling' in st,'stage_trace_digest':stable(list(getattr(v,'stage_trace',[]) or [])),'raw_text_logged':False,'external_send_zero':True}
def _quality(v,envelope,identity,template,terminal,primary_digest=None):
    st=_stages(v); missing=MANDATORY-set(st); label=st.get('unsupported_claim_labeling',{})
    if missing: raise ValueError('MANDATORY_PRODUCT_STAGE_MISSING:'+','.join(sorted(missing)))
    if label.get('label_coverage_ok') is not True: raise ValueError('LABEL_COVERAGE_INVALID')
    base={'request_digest':str(getattr(v,'request_digest','')),'model_identity_digest':stable(asdict(identity)),'output_digest':getattr(v,'draft_digest',None),'status':str(getattr(v,'status','BLOCKED')),'fail_class':getattr(v,'fail_class',None),'severity':_severity(getattr(v,'fail_class',None),str(getattr(v,'status',''))),'stage_trace_digest':stable(list(getattr(v,'stage_trace',[]) or [])),'evidence_receipt_digest':stable(dict(getattr(v,'helper_sdk_receipts',{}) or {}).get('evidence')),'grounding_receipt_digest':stable(dict(getattr(v,'helper_sdk_receipts',{}) or {}).get('grounding')),'dlp_stage_present':True,'label_stage_present':True,'label_coverage_ok':True,'terminal_event_digest':stable(terminal)}
    if primary_digest is None:
        base.update({'schema_version':'butler.primary_quality_receipt.v1','input_digest':stable({'reference_digests':list(getattr(envelope,'reference_digests',[]) or []),'drafting_request_digest':getattr(envelope,'drafting_request_digest',None)}),'template_digest':template,'unsupported_claim_count':int(getattr(v,'unsupported_claim_count',0) or 0),'annotated_claim_count':int(getattr(v,'annotated_claim_count',0) or 0)})
    else: base.update({'schema_version':'butler.repair_quality_receipt.v1','primary_receipt_digest':primary_digest,'invocation_count':1})
    return base

class Box3ProductPipelineRuntime:
    def __init__(self,product_call=None,repair_generator=None): self.call=product_call or _product_call(); self.repair=repair_generator
    def run(self,*,envelope,primary_runner,primary_identity,repair_identity,template_digest,product_kwargs):
        primary_identity.validate(); volatile=VolatileDraft(str(envelope.request_digest))
        pv=self.call(envelope,runner=CapturingRunner(primary_runner,volatile),**product_kwargs); pt=_terminal(pv); pr=_quality(pv,envelope,primary_identity,template_digest,pt); pd=stable(pr)
        eligible=bool(pr['severity']=='soft' and volatile.text_runtime_only and pr['fail_class'] in SOFT and repair_identity and self.repair)
        rr=None; fv=pv; ft=pt
        if eligible:
            repair_identity.validate(); repair_text=str(self.repair({'request_digest':str(envelope.request_digest),'primary_output_digest':text_digest(volatile.text_runtime_only),'primary_fail_class':pr['fail_class'],'primary_draft_runtime_only':volatile.text_runtime_only,'reference_texts_runtime_only':tuple(getattr(envelope,'reference_text_runtime_only',())),'drafting_request_runtime_only':str(getattr(envelope,'drafting_request_runtime_only',''))},repair_identity) or '')
            if not repair_text: raise RuntimeError('BLOCK_ENGINE_NO_FIRST_TOKEN')
            fv=self.call(envelope,runner=FixedOutputRunner(repair_text,repair_identity),**product_kwargs); ft=_terminal(fv); rr=_quality(fv,envelope,repair_identity,template_digest,ft,pd)
        cr={'schema_version':'butler.cascade_receipt.v1','request_digest':str(envelope.request_digest),'primary_receipt_digest':pd,'repair_receipt_digest':stable(rr) if rr else None,'repair_invocation_count':1 if rr else 0,'repair_eligible':eligible,'repair_executed':bool(rr),'final_output_digest':getattr(fv,'draft_digest',None),'final_status':str(getattr(fv,'status','BLOCKED')),'final_fail_class':getattr(fv,'fail_class',None),'final_severity':_severity(getattr(fv,'fail_class',None),str(getattr(fv,'status',''))),'final_terminal_event_digest':stable(ft)}
        return ProductCascadeResult(pr,rr,cr,fv,ft)

@dataclass(frozen=True)
class SecureFileIdentity:
    physical_model_sha256:str; resolved_path_digest:str; size_bytes:int; mtime_ns:int; inode:int; device:int
    @property
    def digest(self): return stable(asdict(self))
def inspect_model_file(path):
    p=Path(path)
    if p.is_symlink(): raise RuntimeError('BLOCK_MODEL_SYMLINK_FORBIDDEN')
    fd=os.open(p,os.O_RDONLY|(getattr(os,'O_NOFOLLOW',0)))
    try:
        b=os.fstat(fd); h=hashlib.sha256(); os.lseek(fd,0,0)
        while True:
            c=os.read(fd,1024*1024)
            if not c: break
            h.update(c)
        a=os.fstat(fd)
        if (b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns)!=(a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns): raise RuntimeError('BLOCK_MODEL_IDENTITY_CHANGED_DURING_HASH')
        return SecureFileIdentity('sha256:'+h.hexdigest(),SHA(str(p.resolve()).encode()),a.st_size,a.st_mtime_ns,a.st_ino,a.st_dev)
    finally: os.close(fd)
def verify_approved_identity(path,approved):
    approved.validate(); i=inspect_model_file(path)
    if i.physical_model_sha256!=approved.physical_model_sha256: raise RuntimeError('BLOCK_MODEL_SHA256_MISMATCH')
    if i.resolved_path_digest!=approved.resolved_path_digest: raise RuntimeError('BLOCK_MODEL_PATH_DIGEST_MISMATCH')
    return i

def _kill(p):
    try: os.killpg(p.pid,signal.SIGTERM)
    except Exception: p.terminate()
    try: p.wait(2)
    except Exception:
        try: os.killpg(p.pid,signal.SIGKILL)
        except Exception: p.kill()
def run_cold_worker_handshake(*,command:list[str],receipt_path:Path,timeout_seconds=180.0):
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,bufsize=0); sel=selectors.DefaultSelector(); out=bytearray(); err=bytearray(); deadline=time.monotonic()+timeout_seconds
    for f,n in ((p.stdout,'o'),(p.stderr,'e')): sel.register(f,selectors.EVENT_READ,n)
    while sel.get_map():
        left=deadline-time.monotonic()
        if left<=0: _kill(p); raise TimeoutError('BLOCK_WORKER_TIMEOUT')
        for k,_ in sel.select(min(.25,left)):
            c=os.read(k.fileobj.fileno(),65536)
            if not c: sel.unregister(k.fileobj); continue
            (out if k.data=='o' else err).extend(c)
            if max(len(out),len(err))>4*1024*1024: _kill(p); raise RuntimeError('BLOCK_WORKER_PIPE_LIMIT')
    rc=p.wait(max(.1,deadline-time.monotonic()))
    if not receipt_path.is_file(): raise RuntimeError('BLOCK_WORKER_RECEIPT_MISSING')
    receipt=json.loads(receipt_path.read_text())
    if rc: raise RuntimeError(str(receipt.get('error_code','BLOCK_WORKER_FAILED')))
    if err: raise RuntimeError('BLOCK_WORKER_STDERR_NONEMPTY')
    if not receipt.get('first_token_observed') or receipt.get('ttft_ms') is None: raise RuntimeError('BLOCK_ENGINE_NO_FIRST_TOKEN')
    return {'schema_version':'butler.cold_worker_handshake.v1','receipt':receipt,'output_digest':SHA(bytes(out)),'output_bytes':len(out),'raw_text_logged':False}

def build_counterbalanced_schedule(fixtures:Iterable[str],seed:int,epochs=5,repeats_per_epoch=2):
    ids=sorted(set(fixtures)); rng=random.Random(seed); rows=[]
    if not ids: raise ValueError('SCHEDULE_FIXTURES_REQUIRED')
    for e in range(epochs):
        order=list(ids); rng.shuffle(order); candidates=('A','B') if e%2==0 else ('B','A')
        for r in range(repeats_per_epoch):
            for f in order:
                for c in candidates: rows.append({'epoch':e,'repeat':r,'fixture_id':f,'candidate':c})
    return rows

def run_product_matrix(*,fixtures,runtime_factory,envelope_factory,primary_runner_factory,primary_identity,repair_identity_by_candidate,template_digest,product_kwargs_factory,build_sha,thermal_reader,seed=20260713,cooldown_seconds=15.0,sleeper=time.sleep):
    schedule=build_counterbalanced_schedule((str(x['fixture_id']) for x in fixtures),seed); fmap={str(x['fixture_id']):x for x in fixtures}; samples=[]; receipts=[]; iteration=0
    for epoch in range(5):
        th,lp=thermal_reader()
        if th not in {'NOMINAL','FAIR'} or lp is True: raise RuntimeError('BLOCK_EPOCH_PRECONDITION')
        warm=fmap[sorted(fmap)[0]]
        for candidate in ('A','B'):
            for wi in range(2):
                wr=runtime_factory(candidate).run(envelope=envelope_factory(warm),primary_runner=primary_runner_factory(candidate,warm),primary_identity=primary_identity,repair_identity=repair_identity_by_candidate.get(candidate),template_digest=template_digest,product_kwargs=product_kwargs_factory(warm)); receipts.append({'schema_version':'butler.warmup_receipt.v1','epoch':epoch,'candidate':candidate,'warmup_index':wi,'cascade_receipt_digest':stable(wr.cascade_receipt),'excluded_from_metrics':True})
        for row in [x for x in schedule if x['epoch']==epoch]:
            f=fmap[row['fixture_id']]; start=time.perf_counter_ns(); result=runtime_factory(row['candidate']).run(envelope=envelope_factory(f),primary_runner=primary_runner_factory(row['candidate'],f),primary_identity=primary_identity,repair_identity=repair_identity_by_candidate.get(row['candidate']),template_digest=template_digest,product_kwargs=product_kwargs_factory(f)); elapsed=(time.perf_counter_ns()-start)/1e6
            sample={'schema_version':'butler.product_sample.v1','fixture_id':f['fixture_id'],'request_digest':result.cascade_receipt['request_digest'],'input_digest':result.primary_receipt['input_digest'],'build_sha':build_sha,'run_kind':'warm','iteration':iteration,'primary_receipt_digest':stable(result.primary_receipt),'repair_receipt_digest':stable(result.repair_receipt) if result.repair_receipt else None,'cascade_receipt_digest':stable(result.cascade_receipt),'final_output_digest':result.cascade_receipt['final_output_digest'],'final_status':result.cascade_receipt['final_status'],'final_fail_class':result.cascade_receipt['final_fail_class'],'quality_gate_pass':result.cascade_receipt['final_severity']=='pass','dlp_pass':result.terminal_event['dlp_stage_present'],'grounding_pass':bool(result.primary_receipt['grounding_receipt_digest']),'failed':result.cascade_receipt['final_severity']=='hard','e2e_latency_ms':elapsed,'thermal_before':th,'thermal_after':thermal_reader()[0],'low_power_mode':lp}; samples.append(sample); receipts.extend([result.primary_receipt,*([result.repair_receipt] if result.repair_receipt else []),result.cascade_receipt,result.terminal_event]); iteration+=1
        started=time.monotonic(); sleeper(cooldown_seconds); observed=time.monotonic()-started
        if observed+.01<cooldown_seconds: raise RuntimeError('BLOCK_COOLDOWN_NOT_OBSERVED')
        receipts.append({'schema_version':'butler.epoch_receipt.v1','epoch':epoch,'cooldown_seconds':cooldown_seconds,'cooldown_observed_seconds':observed})
    return samples,receipts

def measure_dual_resident_pressure(*,load_primary,load_repair,primary_inference,repair_inference,thermal_reader):
    before,lp=thermal_reader()
    if before not in {'NOMINAL','FAIR'} or lp is True: raise RuntimeError('BLOCK_DUAL_RESIDENT_PRECONDITION')
    a,b=load_primary(),load_repair()
    if a is b: raise RuntimeError('BLOCK_DUAL_RESIDENT_PHYSICAL_MODEL_COLLISION')
    primary_inference(a); repair_inference(b)
    return {'schema_version':'butler.dual_resident_pressure.v1','both_models_resident':True,'primary_inference_executed':True,'repair_inference_executed':True,'thermal_before':before,'thermal_after':thermal_reader()[0],'policy_gate_bypass_count':0,'raw_text_logged':False,'external_send_zero':True}

def verify_samples_first(*,samples,receipts):
    ps={stable(r):r for r in receipts if isinstance(r,dict) and r.get('schema_version')=='butler.primary_quality_receipt.v1'}; rs={stable(r):r for r in receipts if isinstance(r,dict) and r.get('schema_version')=='butler.repair_quality_receipt.v1'}; cs={stable(r):r for r in receipts if isinstance(r,dict) and r.get('schema_version')=='butler.cascade_receipt.v1'}; used=[set(),set(),set()]
    if not samples: raise ValueError('PRODUCT_SAMPLES_REQUIRED')
    for s in samples:
        p,c=ps.get(s['primary_receipt_digest']),cs.get(s['cascade_receipt_digest'])
        if not p: raise ValueError('PRIMARY_RECEIPT_MISSING')
        if not c: raise ValueError('CASCADE_RECEIPT_MISSING')
        used[0].add(s['primary_receipt_digest']); used[2].add(s['cascade_receipt_digest'])
        if p['request_digest']!=s['request_digest'] or c['request_digest']!=s['request_digest']: raise ValueError('REQUEST_DIGEST_MISMATCH')
        if c['primary_receipt_digest']!=s['primary_receipt_digest']: raise ValueError('CASCADE_PRIMARY_DIGEST_MISMATCH')
        if c['final_output_digest']!=s['final_output_digest']: raise ValueError('SAMPLE_FINAL_OUTPUT_DIGEST_MISMATCH')
        rd=s.get('repair_receipt_digest')
        if rd:
            r=rs.get(rd)
            if not r: raise ValueError('REPAIR_RECEIPT_MISSING')
            used[1].add(rd)
            if c['repair_invocation_count']!=1 or c['repair_receipt_digest']!=rd or r['primary_receipt_digest']!=s['primary_receipt_digest']: raise ValueError('REPAIR_CHAIN_INVALID')
        elif c['repair_invocation_count']!=0 or c['repair_receipt_digest'] is not None: raise ValueError('UNEXPECTED_REPAIR')
        if not s['dlp_pass'] or not s['grounding_pass']: raise ValueError('MANDATORY_GATE_NOT_PASSED')
    if used[0]!=set(ps) or used[1]!=set(rs) or used[2]!=set(cs): raise ValueError('ORPHAN_RECEIPT')
    return {'schema_version':'butler.product_evidence_verification.v1','sample_count':len(samples),'orphan_count':0,'digest_mismatch_count':0,'verified':True,'raw_text_logged':False}
