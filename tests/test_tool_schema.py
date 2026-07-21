from app.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter


class TestToolDefinitionToToolDescription:
    def test_basic_structure(self):
        tool = ToolDefinition(
            name="my_tool",
            description="Does something",
            category=ToolCategory.UTILITY,
        )
        desc = tool.to_tool_description()
        assert desc["type"] == "function"
        assert desc["function"]["name"] == "my_tool"
        assert desc["function"]["description"] == "Does something"
        assert desc["function"]["parameters"] == {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def test_required_and_optional_parameters(self):
        tool = ToolDefinition(
            name="my_tool",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="req_param", description="required", type="string", required=True),
                ToolParameter(name="opt_param", description="optional", type="integer", required=False),
            ],
        )
        desc = tool.to_tool_description()
        props = desc["function"]["parameters"]["properties"]
        required = desc["function"]["parameters"]["required"]

        assert set(props.keys()) == {"req_param", "opt_param"}
        assert required == ["req_param"]
        assert props["req_param"] == {"type": "string", "description": "required"}
        assert props["opt_param"] == {"type": "integer", "description": "optional"}

    def test_parameter_schema_is_merged_into_property(self):
        tool = ToolDefinition(
            name="my_tool",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(
                    name="items",
                    description="a list",
                    type="array",
                    schema={"items": {"type": "string"}},
                ),
            ],
        )
        desc = tool.to_tool_description()
        prop = desc["function"]["parameters"]["properties"]["items"]
        assert prop["type"] == "array"
        assert prop["description"] == "a list"
        assert prop["items"] == {"type": "string"}

    def test_defaults(self):
        tool = ToolDefinition(name="t", description="d", category=ToolCategory.UTILITY)
        assert tool.enabled is True
        assert tool.requires_confirmation is False
        assert tool.parameters == []
        assert tool.tags == []

    def test_two_instances_do_not_share_mutable_default_lists(self):
        t1 = ToolDefinition(name="t1", description="d", category=ToolCategory.UTILITY)
        t2 = ToolDefinition(name="t2", description="d", category=ToolCategory.UTILITY)
        t1.tags.append("x")
        t1.parameters.append(
            ToolParameter(name="p", description="d", type="string")
        )
        assert t2.tags == []
        assert t2.parameters == []
