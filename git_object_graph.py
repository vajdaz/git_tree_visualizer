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
        self.branches: List[Tuple[str, str, str]] = []  # list of (branch_name, branch_type, commit_hash)
        self.upstreams: Dict[str, str] = {}  # local_branch -> upstream (remote) branch name
        
    def get_all_git_objects(self) -> List[str]:
        """Get all object hashes known by git."""
        try:
            result = subprocess.run(
                ['git', 'cat-file', '--batch-check', '--batch-all-objects'],
                input='',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
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
    
    def get_all_branches(self) -> None:
        """
        Get all local and remote branches and their commit references.
        Stores results in self.branches as (name, type, commit_hash).
        """
        try:
            # Get local branches
            result = subprocess.run(
                ['git', 'branch', '--format=%(refname:short)'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True
            )
            for branch_name in result.stdout.strip().split('\n'):
                if not branch_name or branch_name.startswith('('):
                    # Skip empty lines and the "(HEAD detached at ...)" line
                    continue
                # Get full commit hash for this branch
                hash_result = subprocess.run(
                    ['git', 'rev-parse', f'{branch_name}^{{commit}}'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=True
                )
                commit_hash = hash_result.stdout.strip()
                if commit_hash:
                    self.branches.append((branch_name, 'local', commit_hash))
        except subprocess.CalledProcessError:
            pass

        # Try to discover upstream (tracking) relationships for local branches
        try:
            result = subprocess.run(
                ['git', 'for-each-ref', '--format=%(refname:short) %(upstream:short)', 'refs/heads'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True
            )
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split()
                # Format: "local_branch upstream_branch" (upstream may be absent)
                if len(parts) >= 2:
                    local = parts[0]
                    upstream = parts[1]
                    if upstream:
                        self.upstreams[local] = upstream
        except subprocess.CalledProcessError:
            pass
        
        try:
            # Get remote branches
            result = subprocess.run(
                ['git', 'branch', '-r', '--format=%(refname:short)'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True
            )
            for branch_name in result.stdout.strip().split('\n'):
                if not branch_name or ' -> ' in branch_name:
                    continue
                # Get full commit hash for this branch
                hash_result = subprocess.run(
                    ['git', 'rev-parse', f'{branch_name}^{{commit}}'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=True
                )
                commit_hash = hash_result.stdout.strip()
                if commit_hash:
                    self.branches.append((branch_name, 'remote', commit_hash))
        except subprocess.CalledProcessError:
            pass
    
    def get_head_reference(self) -> None:
        """
        Get the HEAD reference.
        HEAD points to a branch (or commit if detached).
        Returns either a branch name or a commit hash.
        """
        try:
            # Try to get the symbolic reference (branch that HEAD points to)
            result = subprocess.run(
                ['git', 'symbolic-ref', '--short', 'HEAD'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            if result.returncode == 0:
                # HEAD points to a branch
                branch_name = result.stdout.strip()
                if branch_name:
                    # Store HEAD as pointing to this branch
                    self.branches.append(('HEAD', 'head', f'branch:{branch_name}'))
            else:
                # HEAD is detached, get the commit hash
                hash_result = subprocess.run(
                    ['git', 'rev-parse', 'HEAD^{commit}'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=True
                )
                commit_hash = hash_result.stdout.strip()
                if commit_hash:
                    # Store HEAD as pointing directly to a commit
                    self.branches.append(('HEAD', 'head', f'commit:{commit_hash}'))
        except subprocess.CalledProcessError:
            pass
    
    def get_object_type(self, git_hash: str) -> str:
        """Get the type of a Git object."""
        if git_hash in self.object_types:
            return self.object_types[git_hash]
        
        try:
            result = subprocess.run(
                ['git', 'cat-file', '-t', git_hash],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
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
    
    def create_branch_node(self, branch_name: str, branch_type: str) -> str:
        """Create a unique node ID for a branch. Replaces slashes and special chars."""
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', branch_name)
        return f"branch_{branch_type}_{safe_name}"
    
    def process_branches(self) -> None:
        """
        Create nodes for all branches and edges to their commit objects.
        HEAD is handled specially as it can point to a branch or commit.
        """
        # First, create all branch nodes (local and remote)
        for branch_name, branch_type, commit_hash_or_ref in self.branches:
            if branch_type in ('local', 'remote'):
                # Regular branches - create node and edge to commit
                node_id = self.create_branch_node(branch_name, branch_type)
                self.nodes[node_id] = ('branch', branch_name, branch_type)
                
                commit_node_id = self.create_node_id(commit_hash_or_ref)
                self.edges.append((node_id, commit_node_id, branch_type))
        
        # Then handle HEAD separately
        for branch_name, branch_type, commit_hash_or_ref in self.branches:
            if branch_type == 'head':
                node_id = self.create_branch_node(branch_name, branch_type)
                self.nodes[node_id] = ('branch', branch_name, branch_type)

                # Handle HEAD specially - it may point to a branch or a commit
                if commit_hash_or_ref.startswith('branch:'):
                    # HEAD points to a branch
                    target_branch = commit_hash_or_ref.split(':', 1)[1]
                    target_node_id = self.create_branch_node(target_branch, 'local')

                    # If the branch does not actually exist in the graph (no ref yet),
                    # create a dashed "missing" dummy node to represent it.
                    if target_node_id not in self.nodes:
                        # Mark missing local branch so we can style it differently
                        self.nodes[target_node_id] = ('branch', target_branch, 'local_missing')

                    self.edges.append((node_id, target_node_id, 'head'))
                elif commit_hash_or_ref.startswith('commit:'):
                    # HEAD is detached, pointing to a commit
                    commit_hash = commit_hash_or_ref.split(':', 1)[1]
                    commit_node_id = self.create_node_id(commit_hash)
                    self.edges.append((node_id, commit_node_id, 'head'))

        # Add tracking edges for local branches that have an upstream configured.
        # Prefer linking to a remote branch node if present, otherwise link to any matching branch node.
        for local_branch, upstream in self.upstreams.items():
            local_node_id = self.create_branch_node(local_branch, 'local')
            # Prefer remote upstream node id
            upstream_remote_id = self.create_branch_node(upstream, 'remote')
            upstream_local_id = self.create_branch_node(upstream, 'local')

            target_node_id = None
            if upstream_remote_id in self.nodes:
                target_node_id = upstream_remote_id
            elif upstream_local_id in self.nodes:
                target_node_id = upstream_local_id

            if target_node_id and local_node_id in self.nodes:
                # Dashed arrow to indicate tracking relationship
                self.edges.append((local_node_id, target_node_id, 'tracks'))
    
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
        branch_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'branch']
        commit_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'commit']
        tree_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'tree']
        blob_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'blob']
        tag_nodes = [nid for nid, (ntype, _, _) in self.nodes.items() if ntype == 'tag']
        
        if branch_nodes:
            dot_lines.append('  // Branch nodes')
            for node_id in branch_nodes:
                _, label, branch_type = self.nodes[node_id]
                if branch_type == 'local':
                    dot_lines.append(
                        f'  {node_id} [label="{label}", fillcolor="#FFB6C1", shape="cds"];'
                    )
                elif branch_type == 'remote':
                    dot_lines.append(
                        f'  {node_id} [label="{label}", fillcolor="#DDA0DD", shape="cds"];'
                    )
                elif branch_type == 'head':
                    dot_lines.append(
                        f'  {node_id} [label="{label}", fillcolor="#FF6347", shape="cds", penwidth="3"];'
                    )
                elif branch_type == 'local_missing':
                    # Visualize missing (non-existent) local branch with dashed outline
                    dot_lines.append(
                        f'  {node_id} [label="{label}", fillcolor="#FFEFD5", shape="cds", style="dashed,filled"];'
                    )
                
        if commit_nodes:
            dot_lines.append('  // Commit objects')
            for node_id in commit_nodes:
                _, label, _ = self.nodes[node_id]
                dot_lines.append(
                    f'  {node_id} [label="{label}", fillcolor="#FFD700", shape="ellipse"];'
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
                        f'  {from_id} -> {to_id} [color="red"];'
                    )
                elif rel_type == 'tree':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [color="green"];'
                    )
                elif rel_type == 'object':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [color="purple"];'
                    )
                elif rel_type == 'local':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="local", color="orange"];'
                    )
                elif rel_type == 'remote':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="remote", color="brown"];'
                    )
                elif rel_type == 'local_missing':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="local (missing)", color="orange", style="dashed"];'
                    )
                elif rel_type == 'head':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [color="red", penwidth="2"];'
                    )
                elif rel_type == 'tracks':
                    dot_lines.append(
                        f'  {from_id} -> {to_id} [label="tracks", style="dashed", color="black"];'
                    )
                else:
                    dot_lines.append(f'  {from_id} -> {to_id};')
        
        dot_lines.append('}')
        return '\n'.join(dot_lines)
    
    def visualize(self, output_file: str = None, dot_output_file: str = None) -> str:
        """
        Perform the full visualization process.
        Returns the Graphviz DOT content and optionally writes to file.
        Runs dot to generate SVG output if dot_output_file is specified.
        """
        # Get all git objects
        print("Scanning git repository for all objects...", file=sys.stderr)
        all_objects = self.get_all_git_objects()
        
        if not all_objects:
            print("Error: No git objects found", file=sys.stderr)
            sys.exit(1)
        
        print(f"Found {len(all_objects)} git objects", file=sys.stderr)
        
        # Get all branches and HEAD
        print("Scanning git branches and HEAD...", file=sys.stderr)
        self.get_all_branches()
        self.get_head_reference()
        
        # First pass: scan all tree objects to discover names
        self.scan_all_references(all_objects)
        
        # Process all objects
        print("Processing objects and building graph...", file=sys.stderr)
        for i, obj_hash in enumerate(all_objects, 1):
            if i % 100 == 0:
                print(f"  Processed {i}/{len(all_objects)} objects...", file=sys.stderr)
            self.process_object(obj_hash)
        
        # Process branches
        print("Adding branches to graph...", file=sys.stderr)
        self.process_branches()
        
        print(f"Graph contains {len(self.nodes)} nodes and {len(self.edges)} edges",
              file=sys.stderr)
        
        # Generate Graphviz output
        dot_content = self.generate_graphviz()
        
        # Write to file if specified
        if output_file:
            Path(output_file).write_text(dot_content)
            print(f"Graphviz file written to: {output_file}", file=sys.stderr)
        
        # Run dot to generate SVG if dot_output_file is specified
        if dot_output_file:
            print(f"Generating SVG with dot...", file=sys.stderr)
            try:
                result = subprocess.run(
                    ['dot', '-Tsvg', f'-o{dot_output_file}'],
                    input=dot_content,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=True
                )
                print(f"SVG file written to: {dot_output_file}", file=sys.stderr)
            except subprocess.CalledProcessError as e:
                print(f"Error running dot: {e.stderr}", file=sys.stderr)
                sys.exit(1)
            except FileNotFoundError:
                print("Error: 'dot' command not found. Please install Graphviz.", file=sys.stderr)
                sys.exit(1)
        
        return dot_content


def main():
    # Parse command line arguments
    output_file = None
    dot_output_file = 'objects.svg'  # Default SVG output file
    
    if len(sys.argv) > 1:
        # First argument is SVG output file (optional) or --no-svg flag
        if sys.argv[1] == '--no-svg':
            dot_output_file = None
        else:
            dot_output_file = sys.argv[1]
    
    if len(sys.argv) > 2:
        # Second argument is optional DOT file
        output_file = sys.argv[2]
    
    visualizer = GitObjectGraphVisualizer()
    dot_content = visualizer.visualize(output_file, dot_output_file)
    
    # Only print DOT to stdout if SVG generation is disabled
    if not dot_output_file:
        print(dot_content)


if __name__ == '__main__':
    main()
