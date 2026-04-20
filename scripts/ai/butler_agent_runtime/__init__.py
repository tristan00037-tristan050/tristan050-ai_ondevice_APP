from .runtime_contracts import DeviceProfile, ModelSpec, PolicyConfig, ScanResult, BlockResult, AgentResponse, TaskDecision, LoadMeta, SessionRecord, RuntimeReport

__all__ = [
    'DeviceProfile', 'ModelSpec', 'PolicyConfig', 'ScanResult', 'BlockResult',
    'AgentResponse', 'TaskDecision', 'LoadMeta', 'SessionRecord', 'RuntimeReport', 'ButlerAgent'
]


def __getattr__(name):
    if name == 'ButlerAgent':
        from .agent_core import ButlerAgent
        return ButlerAgent
    raise AttributeError(name)
