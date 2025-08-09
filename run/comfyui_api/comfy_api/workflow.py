from typing import Dict, Any, List, Union

class ComfyWorkflow:
    def __init__(self, workflow_json_path: str):
        self.workflow_json_path = workflow_json_path
        self._replacements: Dict[str, Dict[str, Any]] = {}
        self._output_nodes: Dict[str, List[str]] = {}

    def add_replacement(self, node_id: str, input_name: str, value: Any):
        if node_id not in self._replacements:
            self._replacements[node_id] = {}
        self._replacements[node_id][input_name] = value
        return self

    def add_output_node(self, node_id: str, selectors: Union[str, List[str], None] = None):
        if node_id not in self._output_nodes:
            self._output_nodes[node_id] = []

        if selectors is None:
            # 使用特殊标识符代表默认行为
            if "DEFAULT_DOWNLOAD" not in self._output_nodes[node_id]:
                self._output_nodes[node_id].append("DEFAULT_DOWNLOAD")
        elif isinstance(selectors, list):
            self._output_nodes[node_id].extend(s for s in selectors if s not in self._output_nodes[node_id])
        elif isinstance(selectors, str):
            if selectors not in self._output_nodes[node_id]:
                self._output_nodes[node_id].append(selectors)
        return self