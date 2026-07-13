from types import SimpleNamespace
import pytest
from butler_pc_core.model_tier.benchmark_v23.core import *

class E:
    request_digest='sha256:'+'3'*64
    reference_digests=('sha256:'+'4'*64,)
    drafting_request_digest='sha256:'+'5'*64
    reference_text_runtime_only=('근거',)
    drafting_request_runtime_only='작성'

def identity(v):
    return ApprovedModelIdentity(v,'sha256:'+'1'*64,'sha256:'+'2'*64,stable({'x':1}))

def verdict(output,fail,status):
    stages=[
        {'stage':'helper7_parse_evidence'},
        {'stage':'draft_runner_helper3_helper5_stack'},
        {'stage':'unsupported_claim_labeling','label_coverage_ok':True},
        {'stage':'human_approval'},
        {'stage':'dlp_pre_output_guard'},
        {'stage':'final_gate'},
    ]
    return SimpleNamespace(
        request_digest=E.request_digest,status=status,fail_class=fail,
        draft_digest=text_digest(output) if output else None,stage_trace=stages,
        helper_sdk_receipts={'evidence':{'x':1},'grounding':{'x':2}},
        unsupported_claim_count=0,annotated_claim_count=0,
    )

def test_same_request_soft_repair_uses_product_pipeline_twice():
    calls=[]
    def call(e,runner,**kw):
        out=runner(e); calls.append(out)
        return verdict(out,'NEEDS_REVIEW_CONTENT_DRIFT','REAL_CANDIDATE') if len(calls)==1 else verdict(out,None,'PASS')
    result=Box3ProductPipelineRuntime(call,lambda req,ident:'repair').run(
        envelope=E(),primary_runner=lambda e:'primary',primary_identity=identity('1p7'),
        repair_identity=identity('4b'),template_digest='sha256:'+'6'*64,product_kwargs={})
    assert calls==['primary','repair']
    assert result.cascade_receipt['repair_invocation_count']==1

def test_hard_block_never_invokes_repair():
    invoked=[]
    result=Box3ProductPipelineRuntime(
        lambda e,runner,**kw:verdict('', 'BLOCK_DLP_INPUT','BLOCKED'),
        lambda *a:invoked.append(1),
    ).run(envelope=E(),primary_runner=lambda e:'x',primary_identity=identity('1'),
          repair_identity=identity('4'),template_digest='sha256:'+'6'*64,product_kwargs={})
    assert not invoked
    assert result.cascade_receipt['repair_invocation_count']==0

def test_missing_mandatory_product_stage_blocks():
    value=verdict('x',None,'PASS'); value.stage_trace=value.stage_trace[:-1]
    with pytest.raises(ValueError,match='MANDATORY_PRODUCT_STAGE_MISSING'):
        Box3ProductPipelineRuntime(lambda *a,**k:value).run(
            envelope=E(),primary_runner=lambda e:'x',primary_identity=identity('1'),
            repair_identity=None,template_digest='sha256:'+'6'*64,product_kwargs={})

def test_schedule_replay_and_dual_collision():
    assert build_counterbalanced_schedule(['a','b'],7)==build_counterbalanced_schedule(['a','b'],7)
    model=object()
    with pytest.raises(RuntimeError,match='PHYSICAL_MODEL_COLLISION'):
        measure_dual_resident_pressure(
            load_primary=lambda:model,load_repair=lambda:model,
            primary_inference=lambda x:None,repair_inference=lambda x:None,
            thermal_reader=lambda:('NOMINAL',False))
