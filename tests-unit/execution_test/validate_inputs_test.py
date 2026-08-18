
import pytest
import asyncio
from unittest.mock import MagicMock, patch
import nodes
from execution import validate_inputs

@pytest.mark.asyncio
async def test_validate_inputs_invalid_links():
    # Mock node class mapping
    class MockNode:
        RETURN_TYPES = ("IMAGE",)
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}}

    class MockKSampler:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"latent_image": ("LATENT",)}}
        RETURN_TYPES = ("LATENT",)
        FUNCTION = "sample"

    # We need to inject these into nodes.NODE_CLASS_MAPPINGS
    original_mappings = nodes.NODE_CLASS_MAPPINGS.copy()
    nodes.NODE_CLASS_MAPPINGS["MockNode"] = MockNode
    nodes.NODE_CLASS_MAPPINGS["MockKSampler"] = MockKSampler

    try:
        # Case 1: Index out of range
        prompt = {
            "1": {
                "class_type": "MockNode",
                "inputs": {}
            },
            "2": {
                "class_type": "MockKSampler",
                "inputs": {
                    "latent_image": ["1", 1] # Index 1 is out of range for MockNode
                }
            }
        }

        validated = {}
        result = await validate_inputs("prompt_id", prompt, "2", validated)
        valid, errors, node_id = result
        assert valid is False
        assert any(error["type"] == "invalid_link" for error in errors)
        assert any("Link refers to a non-existent output 1" in error["message"] for error in errors)

        # Case 2: Source node doesn't exist
        prompt_missing_node = {
            "2": {
                "class_type": "MockKSampler",
                "inputs": {
                    "latent_image": ["999", 0] 
                }
            }
        }
        validated = {}
        result = await validate_inputs("prompt_id", prompt_missing_node, "2", validated)
        assert result[0] is False
        assert any("non-existent node 999" in error["message"] for error in result[1])

    finally:
        nodes.NODE_CLASS_MAPPINGS.clear()
        nodes.NODE_CLASS_MAPPINGS.update(original_mappings)
