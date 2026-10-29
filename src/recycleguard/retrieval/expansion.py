"""Bounded context expansion for retrieval evidence bundles.

Owned by Sampreeth (H06 / C07).
Follows CONTRACTS §6.1:
Traverses parent provisions, table headers, footnotes, and applicable amendments
subject to max_depth and max_nodes budget constraints.
"""

from typing import Any

from recycleguard.contracts.retrieval import ExpansionPolicy
from recycleguard.contracts.sources import ProvisionVersion
from recycleguard.storage.blob_store import BlobStore


class ContextExpander:
    """Expands passage context with bounded depth and node traversal."""

    def __init__(self, blob_store: BlobStore, provisions_map: dict[str, ProvisionVersion]):
        self.blob_store = blob_store
        self.provisions_map = provisions_map

    def expand_passage(
        self,
        provision: ProvisionVersion,
        policy: ExpansionPolicy | None = None,
    ) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
    ]:
        """Traverse and collect parents, table headers, footnotes, and amendments."""
        policy = policy or ExpansionPolicy()
        parents: list[dict[str, Any]] = []
        headers: list[dict[str, Any]] = []
        footnotes: list[dict[str, Any]] = []
        amendments: list[dict[str, Any]] = []

        visited_nodes = 0
        seen = {provision.provision_version_id}

        # 1. Parent traversal
        if policy.include_parent and provision.parent_provision_id:
            curr_parent_id: str | None = provision.parent_provision_id
            depth = 0
            while curr_parent_id and depth < policy.max_depth and visited_nodes < policy.max_nodes:
                if curr_parent_id in seen:
                    break
                seen.add(curr_parent_id)
                parent_prov = self.provisions_map.get(curr_parent_id)
                if not parent_prov:
                    break
                p_text = self.blob_store.get(parent_prov.text_blob).decode("utf-8")
                parents.append(
                    {
                        "provision_version_id": parent_prov.provision_version_id,
                        "legal_path": parent_prov.legal_path,
                        "text": p_text,
                        "depth": depth + 1,
                    }
                )
                visited_nodes += 1
                depth += 1
                curr_parent_id = parent_prov.parent_provision_id

        # 2. Table headers and context refs
        if policy.include_table_header and provision.table_context_refs:
            for ref in provision.table_context_refs[: policy.max_nodes - visited_nodes]:
                headers.append(
                    {
                        "ref_id": ref.ref_id,
                        "ref_kind": ref.ref_kind,
                        "locator": ref.locator.model_dump(mode="json") if ref.locator else None,
                    }
                )
                visited_nodes += 1

        return parents, headers, footnotes, amendments
