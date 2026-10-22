"""Testes da knowledge base e sincronização da árvore oficial MLB (sem rede)."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

try:
    from automation import prompt_templates as prompts, sync_categories, ml_ingest
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import prompt_templates as prompts
    import sync_categories, ml_ingest


class KnowledgeTests(unittest.TestCase):
    def test_all_profile_files_exist_and_are_substantial(self):
        data = prompts.load_profiles()
        self.assertGreaterEqual(len(data["profiles"]), 32)
        for slug in data["profiles"]:
            with self.subTest(slug=slug):
                doc = prompts.KNOWLEDGE / "categories" / (slug + ".md")
                self.assertTrue(doc.is_file(), f"Doc ausente: {slug}")
                self.assertGreater(len(doc.read_text(encoding="utf-8")), 180)

    def test_refletores_route_to_lighting(self):
        for name in ("Kit 2 Refletores Super LED 400W", "Refletor LED jardim"):
            with self.subTest(title=name):
                selection = prompts.select_knowledge({"title": name, "category":"casa"})
                self.assertEqual(selection["slug"],"iluminacao_jardim")
                self.assertEqual(selection["reason"],"title_keyword")
                rendered = prompts.make_prompt({"title":name,"category":"casa"})
                self.assertIn("Cenário residencial noturno", rendered)
                self.assertIn("Regras obrigatórias", rendered)

    def test_niches_with_specific_keywords(self):
        examples = [
            ("Notebook gamer RTX", "informatica_gamer"),
            ("Perfume floral 100ml", "beleza_cuidados"),
            ("Furadeira profissional", "ferramentas"),
            ("Carrinho de bebê compacto", "bebes"),
            ("Ração premium para gato", "pet_shop"),
            ("Vestido azul", "moda"),
            ("Arroz branco 5kg", "supermercado"),
            ("Console Xbox", "games"),
            ("Violão acústico", "instrumentos_musicais"),
        ]
        for title, slug in examples:
            with self.subTest(title=title):
                self.assertEqual(prompts.select_knowledge({"title": title})["slug"], slug)

    def test_official_cache_matches_true_root_id_without_guessing(self):
        catalog = json.loads(prompts.MLB_CATEGORIES.read_text(encoding="utf-8"))
        self.assertEqual(catalog["source"], "mercadolibre_official_api")
        self.assertEqual(catalog["site_id"], "MLB")
        self.assertGreaterEqual(len(catalog["categories"]),20)
        entry = next(x for x in catalog["categories"] if x["name"] == "Eletrodomésticos")
        self.assertEqual(prompts.select_knowledge({
            "title": "Produto sem palavras reconhecidas",
            "ml_category_id": entry["id"],
        })["slug"], "eletrodomesticos")
        self.assertEqual(prompts._category_name_for_id("MLB000000000000"), "")

    def test_old_four_categories_still_fallback(self):
        for old, slug in [("casa","casa_moveis"),("tecnologia","tecnologia"),
                          ("organizacao","organizacao"),("lifestyle","lifestyle")]:
            self.assertEqual(prompts.select_knowledge({"category":old})["slug"], slug)

    def test_explicit_allowlisted_slug_and_reject_path_traversal(self):
        self.assertEqual(prompts.select_knowledge({"knowledge_slug":"decoracao"})["slug"],"decoracao")
        with self.assertRaises(ValueError):
            prompts.select_knowledge({"knowledge_slug":"../.env"})

    def test_skill_source_is_read_fresh_each_time(self):
        with tempfile.TemporaryDirectory() as temp:
            tempdir=Path(temp)
            (tempdir/"categories").mkdir()
            (tempdir/"core").mkdir()
            (tempdir/"core"/"guardrails.md").write_text("GUARD TESTE")
            (tempdir/"core"/"composition.md").write_text("COMPOS TESTE")
            (tempdir/"categories"/"decoracao.md").write_text("TEXTO ANTIGO")
            with patch.object(prompts, "KNOWLEDGE", tempdir):
                p={"knowledge_slug":"decoracao","title":"Vaso de cerâmica"}
                self.assertIn("TEXTO ANTIGO",prompts.make_prompt(p))
                (tempdir/"categories"/"decoracao.md").write_text("TEXTO NOVO")
                self.assertIn("TEXTO NOVO",prompts.make_prompt(p))

    def test_item_category_id_only_when_returned_by_official_api(self):
        url="https://produto.mercadolivre.com.br/MLB-6797156948-teste-_JM"
        data={"id":"MLB6797156948","title":"Refletor para Jardim",
              "category_id":"MLB12345678","status":"active","pictures":[]}
        with patch.object(ml_ingest,"_download",return_value=(url,b"","text/html")), \
             patch.object(ml_ingest,"_official_item",return_value=data):
            result=ml_ingest.get_product_metadata(url)
        self.assertEqual(result["ml_category_id"],"MLB12345678")
        self.assertTrue(result["metadata_verified"])

    def test_sync_api_failure_keeps_previous_catalog(self):
        with tempfile.TemporaryDirectory() as path:
            output=Path(path)/"categories.json"
            output.write_text("PRESERVE_ME",encoding="utf-8")
            with patch.object(sync_categories,"fetch_categories",side_effect=HTTPError(
                    sync_categories.API_URL,403,"Forbidden",None,None)):
                code=sync_categories.sync(output=output)
            self.assertEqual(code,2)
            self.assertEqual(output.read_text(encoding="utf-8"),"PRESERVE_ME")

    def test_sync_api_success_creates_timestamped_snapshot(self):
        with tempfile.TemporaryDirectory() as path:
            output=Path(path)/"categories.json"
            with patch.object(sync_categories,"fetch_categories",return_value=[
                {"id":"MLB123","name":"Categoria real mockada"}]):
                self.assertEqual(sync_categories.sync(output=output),0)
            d=json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(d["categories"][0]["id"],"MLB123")
            self.assertTrue(d["retrieved_at"])


if __name__=="__main__":
    unittest.main()
