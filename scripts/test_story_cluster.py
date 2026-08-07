#!/usr/bin/env python3
"""Behavior tests for conservative, link-preserving news story clustering."""
import unittest

from adapters import dedup
from story_cluster import assign_story_clusters


class StoryClusterTests(unittest.TestCase):
    def test_near_duplicate_articles_form_one_story_and_keep_all_links(self):
        first = {
            'title': 'FDA approves Acme drug for rare disease - Reuters',
            'source': 'Reuters',
            'url': 'https://www.reuters.com/acme-drug',
            'importance': 82,
            'content_status': 'fulltext',
        }
        second = {
            'title': 'FDA approves Acme drug for rare disease',
            'source': 'STAT News',
            'url': 'https://www.statnews.com/acme-drug',
            'importance': 76,
            'content_status': 'fulltext',
        }
        categories = {'english': {'Drugs & Therapies': [first, second]}}

        stats = assign_story_clusters(categories, '2026-08-07')

        self.assertEqual(stats['total_articles'], 2)
        self.assertEqual(stats['unique_stories'], 1)
        self.assertTrue(first['story_primary'])
        self.assertFalse(second['story_primary'])
        self.assertEqual(first['related_count'], 1)
        self.assertEqual(first['related_articles'][0]['url'], second['url'])
        self.assertEqual(first['story_id'], second['story_id'])

    def test_distinct_products_with_generic_fda_words_do_not_merge(self):
        first = {
            'title': 'FDA approves Acme drug for rare disease',
            'source': 'Reuters',
            'url': 'https://www.reuters.com/acme',
            'importance': 82,
            'content_status': 'fulltext',
        }
        second = {
            'title': 'FDA approves Bravo drug for rare disease',
            'source': 'Reuters',
            'url': 'https://www.reuters.com/bravo',
            'importance': 81,
            'content_status': 'fulltext',
        }
        categories = {'english': {'Drugs & Therapies': [first, second]}}

        stats = assign_story_clusters(categories, '2026-08-07')

        self.assertEqual(stats['unique_stories'], 2)
        self.assertTrue(first['story_primary'])
        self.assertTrue(second['story_primary'])
        self.assertEqual(first['related_count'], 0)
        self.assertEqual(second['related_count'], 0)

    def test_canonical_article_prefers_higher_importance_then_fulltext(self):
        weaker = {
            'title': 'Acme reports phase 3 trial success in cancer',
            'source': 'Trade Wire',
            'url': 'https://example.com/weaker',
            'importance': 70,
            'content_status': 'fulltext',
        }
        stronger = {
            'title': 'Acme reports phase 3 trial success in cancer - Reuters',
            'source': 'Reuters',
            'url': 'https://example.com/stronger',
            'importance': 90,
            'content_status': 'title_only',
        }
        categories = {'english': {'Drugs & Therapies': [weaker, stronger]}}

        assign_story_clusters(categories, '2026-08-07')

        self.assertFalse(weaker['story_primary'])
        self.assertTrue(stronger['story_primary'])
        self.assertEqual(stronger['related_articles'][0]['url'], weaker['url'])
    def test_same_headline_from_different_publishers_is_preserved_for_clustering(self):
        articles = [
            {'title': 'Acme drug wins FDA approval', 'source': 'Reuters', 'url': 'https://reuters.example/a'},
            {'title': 'Acme drug wins FDA approval', 'source': 'STAT News', 'url': 'https://stat.example/a'},
            {'title': 'Acme drug wins FDA approval', 'source': 'Reuters', 'url': 'https://reuters.example/a?utm=copy'},
        ]

        kept = dedup(articles)

        self.assertEqual([article['url'] for article in kept], [
            'https://reuters.example/a',
            'https://stat.example/a',
        ])
    def test_same_publisher_recollection_is_retained_raw_but_not_shown_as_related_coverage(self):
        first = {
            'title': 'Acme drug wins FDA approval',
            'source': 'Reuters',
            'url': 'https://reuters.example/google-proxy',
            'importance': 70,
            'content_status': 'title_only',
        }
        second = {
            'title': 'Acme drug wins FDA approval - Reuters',
            'source': 'Reuters',
            'url': 'https://reuters.example/direct',
            'importance': 80,
            'content_status': 'fulltext',
        }
        categories = {'english': {'Drugs & Therapies': [first, second]}}

        stats = assign_story_clusters(categories, '2026-08-07')

        self.assertEqual(stats['total_articles'], 2)
        self.assertEqual(stats['unique_stories'], 1)
        self.assertTrue(second['story_primary'])
        self.assertEqual(second['related_count'], 0)
        self.assertEqual(second['suppressed_duplicate_count'], 1)
        self.assertEqual(second['related_articles'], [])
    def test_market_report_template_articles_for_distinct_diseases_do_not_merge(self):
        skeletal = {
            'title': 'Skeletal Dysplasia Drugs Market Overview: Major Segments, Strategic Developments, and Leading Companies - openPR.com',
            'source': 'openPR.com',
            'url': 'https://openpr.example/skeletal',
            'importance': 55,
            'content_status': 'title_only',
        }
        schizophrenia = {
            'title': 'Schizophrenia Drugs Market Overview: Major Segments, Strategic Developments, and Leading Companies - openPR.com',
            'source': 'openPR.com',
            'url': 'https://openpr.example/schizophrenia',
            'importance': 50,
            'content_status': 'title_only',
        }
        categories = {'english': {'Drugs & Therapies': [skeletal, schizophrenia]}}

        stats = assign_story_clusters(categories, '2026-08-07')

        self.assertEqual(stats['unique_stories'], 2)
        self.assertTrue(skeletal['story_primary'])
        self.assertTrue(schizophrenia['story_primary'])


if __name__ == '__main__':
    unittest.main()
