"""Behavior-level tests for the workflow parser."""

import textwrap

import pytest

from server.task.parser import _deep_merge, parse_workflow


class TestParseWorkflowNative:
    def test_single_task(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Task
            metadata:
              name: echo-test
            spec:
              taskType: echo
              data:
                items: ["hello"]
        """)
        wf = parse_workflow(doc, format="native")
        assert len(wf.tasks) == 1
        assert wf.tasks[0].task.spec.taskType == "echo"

    def test_staged_dag(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Workflow
            metadata:
              name: staged
            spec:
              taskType: echo
              stages:
                - name: step_a
                  spec:
                    data:
                      items:
                        - a
                - name: step_b
                  dependsOn: [step_a]
                  spec:
                    data:
                      items:
                        - b
        """)
        wf = parse_workflow(doc, format="native")
        assert len(wf.tasks) == 2
        names = {t.local_name for t in wf.tasks}
        assert names == {"step_a", "step_b"}
        step_b = next(t for t in wf.tasks if t.local_name == "step_b")
        assert len(step_b.depends_on) == 1

    def test_graph_dag(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Workflow
            metadata:
              name: graph-wf
            spec:
              taskType: echo
              data:
                items: ["x"]
              graph:
                nodes:
                  - name: a
                  - name: b
                    dependsOn: [a]
                  - name: c
                    dependsOn: [a, b]
        """)
        wf = parse_workflow(doc, format="native")
        assert len(wf.tasks) == 3
        node_c = next(t for t in wf.tasks if t.graph_node_name == "c")
        assert len(node_c.depends_on) == 2

    def test_malformed_yaml(self) -> None:
        with pytest.raises(Exception):
            parse_workflow("{{not valid yaml", format="native")

    def test_graph_cycle_rejected(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Workflow
            metadata:
              name: cycle
            spec:
              taskType: echo
              data:
                items: ["x"]
              graph:
                nodes:
                  - name: a
                    dependsOn: [b]
                  - name: b
                    dependsOn: [a]
        """)
        with pytest.raises(Exception):
            parse_workflow(doc, format="native")

    def test_self_dependency_rejected(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Workflow
            metadata:
              name: selfref
            spec:
              taskType: echo
              data:
                items: ["x"]
              graph:
                nodes:
                  - name: a
                    dependsOn: [a]
        """)
        with pytest.raises(Exception):
            parse_workflow(doc, format="native")

    def test_duplicate_node_names_rejected(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Workflow
            metadata:
              name: dupes
            spec:
              taskType: echo
              data:
                items: ["x"]
              graph:
                nodes:
                  - name: a
                  - name: a
        """)
        with pytest.raises(Exception):
            parse_workflow(doc, format="native")

    def test_task_load_from_estimated_load(self) -> None:
        doc = textwrap.dedent("""\
            apiVersion: flowmesh/v1
            kind: Task
            metadata:
              name: heavy-task
            spec:
              taskType: echo
              data:
                items: ["x"]
              resources:
                estimatedLoad: 4
        """)
        wf = parse_workflow(doc, format="native")
        assert wf.tasks[0].load == 4


class TestDeepMerge:
    def test_nested_merge(self) -> None:
        dst = {"a": {"x": 1}, "b": 2}
        src = {"a": {"y": 3}, "c": 4}
        result = _deep_merge(dst, src)
        assert result == {"a": {"x": 1, "y": 3}, "b": 2, "c": 4}

    def test_src_overwrites_scalar(self) -> None:
        dst = {"a": 1}
        src = {"a": 2}
        result = _deep_merge(dst, src)
        assert result["a"] == 2

    def test_empty_src(self) -> None:
        dst = {"a": 1}
        result = _deep_merge(dst, {})
        assert result == {"a": 1}
