#!/usr/bin/env python3
"""
Git Tree Visualizer - Creates a Graphviz visualization of a Git tree structure.

This script takes a Git reference (e.g., HEAD^{tree}) and recursively crawls
the tree structure, creating a Graphviz file that can be rendered with 'dot'.
"""

import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set


class GitTreeVisualizer:
    def __init__(self, git_ref: str):
        """Initialize the visualizer with a Git reference."""
        self.git_ref = git_ref
        self.nodes: Dict[str, Tuple[str, str]] = {}  # node_id -> (type, name)
        self.edges: List[Tuple[str, str]] = []  # list of (from, to) tuples
        self.visited: Set[str] = set()  # track visited tree objects to avoid loops
        
    def get_git_object_hash(self, ref: str) -> str:
        """Get the actual hash of a Git reference."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', ref],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error resolving Git reference '{ref}': {e.stderr}", file=sys.stderr)
            sys.exit(1)
            
    def get_object_type(self, git_hash: str) -> str:
        """Get the type of a Git object."""
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-t', git_hash],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"
    
    def parse_tree_contents(self, git_hash: str) -> List[Tuple[str, str, str]]:
        """
        Parse tree contents using 'git cat-file -p'.
        Returns list of tuples: (mode, type, hash, name)
        """
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-p', git_hash],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error reading tree object {git_hash}: {e.stderr}", file=sys.stderr)
            return []
        
        entries = []
        # Parse output: mode type hash\tname
        # Example: 100644 blob abc123\tfile.txt
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            # Split by tab to separate metadata from name
            match = re.match(r'(?P<mode>\d+)\s+(?P<type>\w+)\s+(?P<hash>[a-f0-9]+)\t(?P<name>.+)', line)
            if match:
                mode = match.group('mode')
                obj_type = match.group('type')
                obj_hash = match.group('hash')
                name = match.group('name')
                entries.append((mode, obj_type, obj_hash, name))
        
        return entries
    
    def create_node_id(self, git_hash: str, name: str) -> str:
        """Create a unique node ID for Graphviz."""
        # Use hash and name to create unique ID
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        return f"obj_{git_hash[:8]}_{safe_name}"
    
    def crawl_tree(self, git_hash: str, parent_id: str = None) -> None:
        """Recursively crawl the tree structure."""
        if git_hash in self.visited:
            return
        
        self.visited.add(git_hash)
        
        # Get the tree entries
        entries = self.parse_tree_contents(git_hash)
        
        for mode, obj_type, obj_hash, name in entries:
            node_id = self.create_node_id(obj_hash, name)
            
            # Add node
            if obj_type == 'tree':
                self.nodes[node_id] = ('tree', name)
                # Add edge from parent if it exists
                if parent_id:
                    self.edges.append((parent_id, node_id))
                # Recursively crawl subtrees
                self.crawl_tree(obj_hash, node_id)
            elif obj_type == 'blob':
                self.nodes[node_id] = ('blob', name)
                # Add edge from parent if it exists
                if parent_id:
                    self.edges.append((parent_id, node_id))
    
    def generate_graphviz(self) -> str:
        """Generate Graphviz DOT format output."""
        dot_lines = [
            'digraph gittree {',
            '  rankdir=LR;',
            '  splines=line;',
            '  node [shape=box, style="rounded,filled"];',
            '',
            '  // Tree node styling',
            '  edge [color=gray];',
            ''
        ]
        
        # Define node styles
        tree_nodes = [nid for nid, (ntype, _) in self.nodes.items() if ntype == 'tree']
        blob_nodes = [nid for nid, (ntype, _) in self.nodes.items() if ntype == 'blob']
        
        if tree_nodes:
            dot_lines.append('  // Tree objects (directories)')
            for node_id in tree_nodes:
                _, name = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{name}", fillcolor="#90EE90", shape="folder"];'
                )
        
        if blob_nodes:
            dot_lines.append('  // Blob objects (files)')
            for node_id in blob_nodes:
                _, name = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{name}", fillcolor="#87CEEB", shape="note"];'
                )
        
        # Add edges
        if self.edges:
            dot_lines.append('')
            dot_lines.append('  // Relationships')
            for from_id, to_id in self.edges:
                dot_lines.append(f'  {from_id} -> {to_id};')
        
        dot_lines.append('}')
        return '\n'.join(dot_lines)
    
    def visualize(self, output_file: str = None) -> str:
        """
        Perform the full visualization process.
        Returns the Graphviz DOT content and optionally writes to file.
        """
        # Resolve the git reference to a hash
        tree_hash = self.get_git_object_hash(self.git_ref)
        
        # Verify it's a tree object
        obj_type = self.get_object_type(tree_hash)
        if obj_type != 'tree':
            print(
                f"Error: '{self.git_ref}' resolves to a {obj_type} object, not a tree",
                file=sys.stderr
            )
            sys.exit(1)
        
        # Create root node for the tree
        root_id = self.create_node_id(tree_hash, "root")
        self.nodes[root_id] = ('tree', 'root')
        
        # Crawl the tree structure
        self.crawl_tree(tree_hash, root_id)
        
        # Generate Graphviz output
        dot_content = self.generate_graphviz()
        
        # Write to file if specified
        if output_file:
            Path(output_file).write_text(dot_content)
            print(f"Graphviz file written to: {output_file}")
        
        return dot_content


def main():
    if len(sys.argv) < 2:
        print("Usage: git_tree_visualizer.py <git-ref> [output-file.dot]")
        print("Example: git_tree_visualizer.py HEAD^{{tree}} tree.dot")
        print("         git_tree_visualizer.py HEAD tree_output.dot")
        sys.exit(1)
    
    git_ref = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    visualizer = GitTreeVisualizer(git_ref)
    dot_content = visualizer.visualize(output_file)
    
    # Print to stdout if no output file specified
    if not output_file:
        print(dot_content)


if __name__ == '__main__':
    main()
