"""
==============================================================================
Тестовый комплекс: Wildberries_Fast_Scraper Test Suite
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/Wildberries_Fast_Scraper
Лицензия: MIT License (2026)
Назначение: Автоматизированное тестирование парсинга, demo-режима и экспорта в CSV.
==============================================================================
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Добавление корня проекта в sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import wb_scraper
from wb_scraper import ProductItem, WildberriesScraper, export_to_csv, export_to_json


class TestWildberriesScraper(unittest.TestCase):
    """Набор тестов для автономного скрапера Wildberries."""

    def setUp(self):
        self.scraper = WildberriesScraper()

    def test_demo_catalog_generation(self):
        """Проверка генерации демо-товаров без внешних сетевых запросов."""
        items = self.scraper.generate_demo_catalog(query="кроссовки", count=15)
        self.assertEqual(len(items), 15)
        for item in items:
            self.assertIsInstance(item, ProductItem)
            self.assertTrue(item.sku > 0)
            self.assertTrue(len(item.title) > 0)
            self.assertTrue(len(item.brand) > 0)
            self.assertGreaterEqual(item.price_original, item.price_spp)
            self.assertGreaterEqual(item.total_stock, 0)
            d = item.to_dict()
            self.assertIn("sku", d)
            self.assertIn("title", d)

    def test_csv_export_format(self):
        """Проверка корректности экспорта в CSV (UTF-8 with BOM, разделитель точка с запятой)."""
        items = self.scraper.generate_demo_catalog(query="тест", count=5)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            temp_path = Path(tf.name)

        try:
            export_to_csv(items, temp_path)
            self.assertTrue(temp_path.exists())
            self.assertGreater(temp_path.stat().st_size, 0)

            # Проверка кодировки UTF-8 BOM и разделителя
            with open(temp_path, "rb") as f:
                content = f.read()
                # UTF-8 BOM маркер: \xef\xbb\xbf
                self.assertTrue(content.startswith(b"\xef\xbb\xbf"))

            text = content.decode("utf-8-sig")
            lines = text.strip().split("\n")
            self.assertGreaterEqual(len(lines), 6)  # заголовок + 5 строк
            header = lines[0]
            self.assertIn(";", header)
            self.assertIn("Артикул", header)
            self.assertIn("Наименование", header)
            self.assertIn("Цена с СПП", header)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_json_export_format(self):
        """Проверка структуры экспортируемого JSON."""
        items = self.scraper.generate_demo_catalog(query="тест_json", count=3)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = Path(tf.name)

        try:
            export_to_json(items, temp_path)
            self.assertTrue(temp_path.exists())
            import json
            with open(temp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 3)
            self.assertEqual(data[0]["sku"], items[0].sku)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_http_headers_structure(self):
        """Проверка структуры заголовков для обхода базовой защиты."""
        headers = self.scraper._get_headers()
        self.assertIn("User-Agent", headers)
        self.assertIn("Accept", headers)
        self.assertIn("Accept-Language", headers)
        self.assertTrue("Mozilla" in headers["User-Agent"])


if __name__ == "__main__":
    unittest.main()
