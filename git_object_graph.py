#!/usr/bin/env python3
"""
Git Object Graph Visualizer - Creates a Graphviz visualization of all Git objects.

This script scans all objects known by git (blobs, trees, commits, and tags)
and creates a graph showing their relationships using Graphviz.
"""

import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set


class GitObjectGraphVisualizer:
    def __init__(self):
        """Initialize the visualizer."""
        self.nodes: Dict[str, Tuple[str, str, str]] = {}  # node_id -> (type, label, name)
        self.edges: List[Tuple[str, str, str]] = []  # list of (from, to, label) tuples
        self.visited: Set[str] = set()  # track visited objects
        self.object_types: Dict[str, str] = {}  # hash -> type mapping
        self.object_names: Dict[str, str] = {}  # hash -> name mapping
        
    def get_all_git_objects(self) -> List[str]:
        """Get all object hashes known by git."""
        try:
            result = subprocess.run(
                ['git', 'cat-file', '--batch-command', '--batch-all-objects'],
                input='',
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error getting git objects: {e.stderr}", file=sys.stderr)
            return []
        
        objects = set()
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            # Format is "hash type size"
            parts = line.split()
            if parts:
                objects.add(parts[0])
        
        return list(objects)
    
    def get_object_type(self, git_hash: str) -> str:
        """Get the type of a Git object."""
        if git_hash in self.object_types:
            return self.object_types[git_hash]
        
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-t', git_hash],
                capture_output=True,
                text=True,
                check=True
            )
            obj_type = result.stdout.strip()
            self.object_types[git_hash] = obj_type
            return obj_type
        except subprocess.CalledProcessError:
            return "unknown"
    
    def parse_commit(self, git_hash: str) -> List[Tuple[str, str]]:
        """
        Parse commit object and extract tree and parent references.
        Returns list of tuples: (ref_type, ref_hash)
        """
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-p', git_hash],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError:
            return []
        
        refs = []
        for line in result.stdout.split('\n'):
            if line.startswith('tree '):
                tree_hash = line.split()[1]
                refs.append(('tree', tree_hash))
            elif line.startswith('parent '):
                parent_hash = line.split()[1]
                refs.append(('parent', parent_hash))
        
        return refs
    
    def parse_tree(self, git_hash: str) -> List[Tuple[str, str]]:
        """
        Parse tree object and extract blob/tree references.
        Returns list of tuples: (ref_type, ref_hash)
        Also stores names for child objects.
        """
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-p', git_hash],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError:
            return []
        
        refs = []
        for line in result.stdout.split('\n'):
            if not line:
                continue
            # Parse output: mode type hash\tname
            match = re.match(r'(?P<mode>\d+)\s+(?P<type>\w+)\s+(?P<hash>[a-f0-9]+)\s+(?P<name>.*)', line)
            if match:
                ref_type = match.group('type')
                ref_hash = match.group('hash')
                name = match.group('name')
                # Store the name for this object
                if ref_hash not in self.object_names:
                    self.object_names[ref_hash] = name
                refs.append((ref_type, ref_hash))
        
        return refs
    
    def parse_tag(self, git_hash: str) -> List[Tuple[str, str]]:
        """
        Parse tag object and extract object reference.
        Also stores the tag name if available.
        Returns list of tuples: (ref_type, ref_hash)
        """
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-p', git_hash],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError:
            return []
        
        refs = []
        for line in result.stdout.split('\n'):
            if line.startswith('object '):
                obj_hash = line.split()[1]
                refs.append(('object', obj_hash))
            elif line.startswith('tag '):
                tag_name = line.split(' ', 1)[1]
                # Store the tag name for this tag object
                if git_hash not in self.object_names:
                    self.object_names[git_hash] = tag_name
        
        return refs
    
    def create_node_id(self, git_hash: str) -> str:
        """Create a unique node ID for Graphviz."""
        return f"obj_{git_hash[:8]}"
    
    def scan_all_references(self, all_objects: List[str]) -> None:
        """
        First pass: scan all objects to populate object_names from tree and tag references.
        This ensures names are discovered before processing individual objects.
        """
        print("Scanning object references to discover names...", file=sys.stderr)
        for i, obj_hash in enumerate(all_objects, 1):
            if i % 100 == 0:
                print(f"  Scanned {i}/{len(all_objects)} objects...", file=sys.stderr)
            
            obj_type = self.get_object_type(obj_hash)
            if obj_type == 'tree':
                # Parse tree to extract child names
                self.parse_tree(obj_hash)
            elif obj_type == 'tag':
                # Parse tag to extract tag name
                self.parse_tag(obj_hash)
    
    def process_object(self, git_hash: str) -> None:
        """Process a single Git object and extract its references."""
        if git_hash in self.visited:
            return
        
        self.visited.add(git_hash)
        
        obj_type = self.get_object_type(git_hash)
        node_id = self.create_node_id(git_hash)
        
        # Get name if available (should be populated from first pass)
        name = self.object_names.get(git_hash, "")
        label = f"{git_hash[:8]}\n{name}" if name else git_hash[:8]
        
        # Create node with shortened hash and optional name as label
        self.nodes[node_id] = (obj_type, label, name)
        
        # Extract references based on object type
        refs = []
        if obj_type == 'commit':
            refs = self.parse_commit(git_hash)
        elif obj_type == 'tree':
            refs = self.parse_tree(git_hash)
        elif obj_type == 'tag':
            refs = self.parse_tag(git_hash)
        
        # Process references and create edges
        for ref_type, ref_hash in refs:
            ref_node_id = self.create_node_id(ref_hash)
            self.edges.append((node_id, ref_node_id, ref_type))
            # Recursively process referenced objects
            self.process_object(ref_hash)
    
    def generate_graphviz(self) -> str:
        """Generate Graphviz DOT format output."""
        dot_lines = [
            'digraph gitobjects {',
            '  rankdir=LR;',
            '  splines=line;',
            '  node [shape=box, style="rounded,filled"];',
            '',
            '  // Edge styling',
            '  edge [color=gray];',
            ''
        ]
        
        # Define node styles by type
        commit_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'commit']
        tree_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'tree']
        blob_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'blob']
        tag_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'tag']
        
        if commit_nodes:
            dot_lines.append('  // Commit objects')
            for node_id in commit_nodes:
                _, label, _ = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{label}", fillcolor="#FFD700", shape="box"];'
                )
        
        if tree_nodes:
            dot_lines.append('  // Tree objects')
            for node_id in tree_nodes:
                _, label, _ = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{label}", fillcolor="#90EE90", shape="folder"];'
                )
        
        if blob_nodes:
            dot_lines.append('  // Blob objects')
            for node_id in blob_nodes:
                _, label, _ = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{label}", fillcolor="#87CEEB", shape="note"];'
                )
        
        if tag_nodes:
            dot_lines.append('  // Tag objects')
            for node_id in tag_nodes:
                _, label, _ = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{label}", fillcolor="#FF69B4", shape="diamond"];'
                )
        
        # Add edges with labels
        if self.edges:
            dot_lines.append('')
            dot_lines.append('  // Relationships')
            for from_id, to_id, rel_type in self.edges:
                if rel_type == 'parent':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="{rel_type}", color="red"];'
                    )
                elif rel_type == 'tree':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="{rel_type}", color="green"];'
                    )
                elif rel_type == 'object':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="{rel_type}", color="purple"];'
                    )
                else:
                    dot_lines.append(f'  {from_id} -> {to_id} [label="{rel_type}"];')
        
        dot_lines.append('}')
        return '\n'.join(dot_lines)
    
    def visualize(self, output_file: str = None) -> str:
        """
        Perform the full visualization process.
        Returns the Graphviz DOT content and optionally writes to file.
        """
        # Get all git objects
        print("Scanning git repository for all objects...", file=sys.stderr)
        all_objects = self.get_all_git_objects()
        
        if not all_objects:
            print("Error: No git objects found", file=sys.stderr)
            sys.exit(1)
        
        print(f"Found {len(all_objects)} git objects", file=sys.stderr)
        
        # First pass: scan all tree objects to discover names
        self.scan_all_references(all_objects)
        
        # Process all objects
        print("Processing objects and building graph...", file=sys.stderr)
        for i, obj_hash in enumerate(all_objects, 1):
            if i % 100 == 0:
                print(f"  Processed {i}/{len(all_objects)} objects...", file=sys.stderr)
            self.process_object(obj_hash)
        
        print(f"Graph contains {len(self.nodes)} nodes and {len(self.edges)} edges",
              file=sys.stderr)
        
        # Generate Graphviz output
        dot_content = self.generate_graphviz()
        
        # Write to file if specified
        if output_file:
            Path(output_file).write_text(dot_content)
            print(f"Graphviz file written to: {output_file}", file=sys.stderr)
        
        return dot_content


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    visualizer = GitObjectGraphVisualizer()
    dot_content = visualizer.visualize(output_file)
    
    # Print to stdout if no output file specified
    if not output_file:
        print(dot_content)


if __name__ == '__main__':
    main()
