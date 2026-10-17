"""Tests and benchmarks for the Graph-versus-Baseline comparison."""
import pytest
from app.graph.comparison import baseline_isolated_search, compare_graph_vs_baseline


def test_baseline_isolated_search_finds_no_direct_connection_at_ch4():
    """Verify that an isolated baseline search fails to find a connection between Mara and Halden at Ch 4."""
    res = baseline_isolated_search("c_mara_voss", "c_pavel_halden", chapter=4)
    assert res["connected"] is False
    assert res["path_length"] == 0
    assert "No direct relationship or shared record exists" in res["explanation"]


def test_baseline_isolated_search_finds_direct_connection_at_ch5():
    """Verify that an isolated baseline search finds the direct connection only when Ch 5 SUSPECTS is unlocked."""
    res = baseline_isolated_search("c_mara_voss", "c_pavel_halden", chapter=5)
    assert res["connected"] is True
    assert res["path_length"] == 1
    assert "Mara suspects Halden" in res["explanation"]


def test_graph_vs_baseline_comparison_demonstration():
    """Verify that the graph traversal succeeds where the baseline fails at Chapter 4."""
    comparison = compare_graph_vs_baseline("c_mara_voss", "c_pavel_halden", chapter=4)
    
    # Baseline cannot connect them
    assert comparison["baseline"]["connected"] is False
    
    # Graph connects them via Elias Thorne
    assert comparison["graph"]["connected"] is True
    assert comparison["graph"]["hops"] == 2
    assert "Elias Thorne" in comparison["graph"]["nodes"]
    assert comparison["graph"]["evidence_count"] >= 2
    assert comparison["analysis"]["graph_found_connection"] is True
    assert comparison["analysis"]["baseline_found_connection"] is False
