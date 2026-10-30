"""Workflow-i moraju biti ispravni i za GitHub: bez dupliranih ključeva (PyYAML ih tiho prihvata, GitHub odbacuje ceo fajl)."""
from pathlib import Path

import pytest
import yaml

WORKFLOWI = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


class StrogiLoader(yaml.SafeLoader):
    pass


def _bez_duplikata(loader, cvor, deep=False):
    kljucevi = set()
    for k, _ in cvor.value:
        kljuc = loader.construct_object(k, deep=deep)
        if kljuc in kljucevi:
            raise yaml.constructor.ConstructorError(None, None, f"dupli ključ „{kljuc}“", k.start_mark)
        kljucevi.add(kljuc)
    return loader.construct_mapping(cvor, deep)


StrogiLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _bez_duplikata)


@pytest.mark.parametrize("put", WORKFLOWI, ids=lambda p: p.name)
def test_workflow_bez_duplih_kljuceva(put):
    w = yaml.load(put.read_text(encoding="utf-8"), Loader=StrogiLoader)
    for posao in w["jobs"].values():
        for korak in posao.get("steps", []):
            assert "run" in korak or "uses" in korak, f"{put.name}: korak bez run/uses: {korak.get('name')}"
