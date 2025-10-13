"""Tests for block parsers."""

from hother.cancelable.streaming.blocks.parsers import ActionParser, FileOperationsParser, FilePatchParser, HierarchyParser


class TestActionParser:
    """Test ActionParser."""

    def test_parse_preamble_with_dependencies(self):
        """Test parsing action with dependencies."""
        parser = ActionParser()
        result = parser.parse_preamble("load_data:after(task1, task2)")

        assert result["type"] == "action"
        assert result["parameters"]["action_name"] == "load_data"
        assert result["parameters"]["dependencies"] == ["task1", "task2"]

    def test_parse_preamble_no_dependencies(self):
        """Test parsing action without dependencies."""
        parser = ActionParser()
        result = parser.parse_preamble("process_data")

        assert result["type"] == "action"
        assert result["parameters"]["action_name"] == "process_data"
        assert result["parameters"]["dependencies"] == []

    def test_parse_content_with_parameters(self):
        """Test parsing content with parameters."""
        parser = ActionParser()
        content = """<input>data.csv</input>
<output>results.json</output>
<threshold>0.85</threshold>"""

        result = parser.parse_content(content)
        assert result.parameters["input"] == "data.csv"
        assert result.parameters["output"] == "results.json"
        assert result.parameters["threshold"] == "0.85"

    def test_parse_content_with_references(self):
        """Test parsing content with references."""
        parser = ActionParser()
        content = """<data ref="a:task1" path="$.output"></data>
<config ref="a:task2" path="$.settings">default.json</config>"""

        result = parser.parse_content(content)
        assert "data" in result.references
        assert result.references["data"].ref == "a:task1"
        assert result.references["data"].path == "$.output"
        assert result.references["config"].default_value == "default.json"


class TestFileOperationsParser:
    """Test FileOperationsParser."""

    def test_parse_content(self):
        """Test parsing file operations."""
        parser = FileOperationsParser()
        content = """src/main.py:C
src/utils.py:C
tests/test.py:C
old.py:D
config.yaml:E"""

        result = parser.parse_content(content)
        assert len(result.operations["create"]) == 3
        assert len(result.operations["delete"]) == 1
        assert len(result.operations["edit"]) == 1
        assert result.total_operations == 5
        assert "src" in result.folders

    def test_parse_content_with_errors(self):
        """Test parsing with invalid lines."""
        parser = FileOperationsParser()
        content = """src/main.py:C
invalid_line_no_colon
src/utils.py:X"""

        result = parser.parse_content(content)
        assert len(result.operations["create"]) == 1
        assert len(result.errors) == 2


class TestFilePatchParser:
    """Test FilePatchParser."""

    def test_parse_preamble_replace(self):
        """Test parsing replace operation."""
        parser = FilePatchParser()
        result = parser.parse_preamble("src/main.py:R10-15")

        assert result["parameters"]["file_path"] == "src/main.py"
        assert result["parameters"]["operation"] == "R"
        assert result["parameters"]["line_start"] == 10
        assert result["parameters"]["line_end"] == 15

    def test_parse_preamble_insert_after(self):
        """Test parsing insert after operation."""
        parser = FilePatchParser()
        result = parser.parse_preamble("test.py:I5+")

        assert result["parameters"]["file_path"] == "test.py"
        assert result["parameters"]["operation"] == "I"
        assert result["parameters"]["line_start"] == 5
        assert result["parameters"]["insert_after"] is True

    def test_parse_content_with_code(self):
        """Test parsing content with code block."""
        parser = FilePatchParser()
        content = """```python
def hello():
    return "world"
```"""

        result = parser.parse_content(content)
        assert result.has_code is True
        assert result.language == "python"
        assert "def hello():" in result.code


class TestHierarchyParser:
    """Test HierarchyParser."""

    def test_parse_content_with_root(self):
        """Test parsing hierarchy with root folder."""
        parser = HierarchyParser()
        content = """project/
├── src/
│   ├── main.py
│   └── utils.py
├── tests/
└── README.md"""

        result = parser.parse_content(content)
        assert result.file_count == 3  # main.py, utils.py, README.md
        assert result.folder_count == 2  # src/, tests/ (not counting project/)
        assert result.max_depth > 0
        assert len(result.lines) == 6

    def test_parse_content_without_root(self):
        """Test parsing hierarchy without root folder."""
        parser = HierarchyParser()
        content = """src/
├── main.py
└── utils.py"""

        result = parser.parse_content(content)
        assert result.file_count == 2  # main.py, utils.py
        assert result.folder_count == 0  # src/
        assert len(result.lines) == 3

    def test_parse_content_deeper_hierarchy(self):
        """Test parsing deeper hierarchy."""
        parser = HierarchyParser()
        content = """myproject/
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   └── main.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── tests/
│   └── test_main.py
└── setup.py"""

        result = parser.parse_content(content)
        assert result.file_count == 6  # All .py files
        assert result.folder_count == 4  # src/, core/, utils/, tests/
        assert result.max_depth >= 2
