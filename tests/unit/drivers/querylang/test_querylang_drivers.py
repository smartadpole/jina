import unittest

from jina.executors.crafters import BaseSegmenter
from jina.flow import Flow
from jina.proto import jina_pb2
from tests import JinaTestCase


def random_docs(num_docs):
    for j in range(num_docs):
        d = jina_pb2.Document()
        d.id = j
        d.text = 'hello world'
        d.uri = 'doc://'
        for m in range(10):
            dm = d.matches.add()
            dm.text = 'match to hello world'
            dm.uri = 'doc://match'
            dm.id = m
            dm.score.ref_id = d.id
            for mm in range(10):
                dmm = dm.matches.add()
                dmm.text = 'nested match to match'
                dmm.uri = 'doc://match/match'
                dmm.id = mm
                dmm.score.ref_id = m
        yield d


def random_docs_with_chunks(num_docs):
    d1 = jina_pb2.Document()
    d1.id = 1
    d1.text = 'chunk1 chunk2'
    yield d1
    d2 = jina_pb2.Document()
    d2.id = 1
    d2.text = 'chunk3'
    yield d2


class DummySegmenter(BaseSegmenter):

    def craft(self, text, *args, **kwargs):
        return [{'text': 'adasd' * (j + 1)} for j in range(10)]


class DummyModeIdSegmenter(BaseSegmenter):

    def craft(self, text, *args, **kwargs):
        if 'chunk3' not in text:
            return [{'text': f'chunk{j + 1}', 'modality': f'mode{j + 1}'} for j in range(2)]
        elif 'chunk3' in text:
            return [{'text': f'chunk3', 'modality': 'mode3'}]


class QueryLangTestCase(JinaTestCase):

    def test_segment_driver(self):
        def validate(req):
            self.assertGreater(req.docs[-1].id, req.docs[0].id)
            self.assertGreater(req.docs[0].matches[-1].id, req.docs[0].matches[0].id)
            self.assertNotEqual(req.docs[0].text, '')
            self.assertNotEqual(req.docs[-1].text, '')
            self.assertNotEqual(req.docs[0].chunks[0].text, '')
            self.assertNotEqual(req.docs[0].matches[0].text, '')
            self.assertNotEqual(req.docs[0].matches[0].matches[-1].text, '')
            self.assertEqual(len(req.docs[0].chunks), 10)
            self.assertEqual(len(req.docs[-1].chunks), 10)
            self.assertEqual(len(req.docs[0].matches), 10)
            self.assertEqual(len(req.docs[-1].matches), 10)
            self.assertEqual(len(req.docs[-1].matches[0].matches), 10)
            self.assertEqual(len(req.docs[-1].matches[-1].matches), 10)

        f = Flow().add(uses='DummySegmenter')

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

    def test_slice_ql(self):
        def validate(req):
            self.assertEqual(len(req.docs), 2)  # slice on level 0
            self.assertEqual(len(req.docs[0].chunks), 2)  # slice on level 1
            self.assertEqual(len(req.docs[-1].chunks), 2)  # slice on level 1
            self.assertEqual(len(req.docs[0].matches), 2)  # slice on level 1 for matches
            self.assertEqual(len(req.docs[-1].matches[0].matches), 2)  # slice on level 2 for matches

        f = (Flow().add(uses='DummySegmenter')
             .add(uses='- !SliceQL | {start: 0, end: 2, traverse_on: ["chunks"], depth_range: [0, 2]}')
             .add(uses='- !SliceQL | {start: 0, end: 2, traverse_on: ["matches"], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

        f = (Flow().add(uses='DummySegmenter')
             .add(uses='- !SliceQL | {start: 0, end: 2, traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

    def test_select_ql(self):
        def validate(req):
            self.assertEqual(req.docs[0].text, '')
            self.assertEqual(req.docs[-1].text, '')
            self.assertEqual(req.docs[0].matches[0].text, '')
            self.assertEqual(req.docs[0].chunks[0].text, '')

        f = (Flow().add(uses='DummySegmenter')
            .add(
            uses='- !SelectQL | {fields: [uri, matches, chunks], traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

        f = (Flow().add(uses='DummySegmenter')
             .add(uses='- !ExcludeQL | {fields: [text], traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

    def test_sort_ql(self):
        def validate(req):
            self.assertLess(req.docs[-1].id, req.docs[0].id)
            self.assertLess(req.docs[0].matches[-1].id, req.docs[0].matches[0].id)
            self.assertLess(req.docs[0].chunks[-1].id, req.docs[0].chunks[0].id)

        f = (Flow().add(uses='DummySegmenter')
            .add(
            uses='- !SortQL | {field: id, reverse: true, traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

        f = (Flow().add(uses='DummySegmenter')
             .add(
            uses='- !SortQL | {field: id, reverse: false, traverse_on: [chunks, matches], depth_range: [0, 2]}')
             .add(uses='- !ReverseQL | {traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

    def test_filter_ql(self):
        def validate(req):
            self.assertEqual(req.docs[0].id, 2)
            self.assertEqual(req.docs[0].matches[0].id, 2)
            self.assertEqual(req.docs[0].matches[0].matches[0].id, 2)

        f = (Flow().add(uses='DummySegmenter')
            .add(
            uses='- !FilterQL | {lookups: {id: 2}, traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)

    def test_filter_ql_modality_wrong_depth(self):
        def validate(req):
            # since no doc has modality mode2 they are all erased from the list of docs
            self.assertEqual(len(req.docs), 0)

        f = (Flow().add(uses='DummyModeIdSegmenter')
            .add(
            uses='- !FilterQL | {lookups: {modality: mode2}, traverse_on: [chunks], depth_range: [0, 1]}'))

        with f:
            f.index(random_docs_with_chunks(2), output_fn=validate, callback_on_body=True)

    def test_filter_ql_modality(self):
        def validate(req):
            # docs are not filtered, so 2 docs are returned, but only the chunk at depth1 with modality mode2 is returned
            self.assertEqual(len(req.docs), 2)
            self.assertEqual(len(req.docs[0].chunks), 1)
            self.assertEqual(len(req.docs[1].chunks), 0)

        f = (Flow().add(uses='DummyModeIdSegmenter')
            .add(
            uses='- !FilterQL | {lookups: {modality: mode2}, traverse_on: [chunks], depth_range: [1, 1]}'))

        with f:
            f.index(random_docs_with_chunks(2), output_fn=validate, callback_on_body=True)

    def test_filter_compose_ql(self):
        def validate(req):
            self.assertEqual(req.docs[0].id, 2)
            self.assertEqual(req.docs[0].matches[0].id, 2)
            self.assertEqual(len(req.docs[0].matches[0].matches), 0)  # match's match does not contain "hello"

        f = (Flow().add(uses='DummySegmenter')
            .add(
            uses='- !FilterQL | {lookups: {id: 2, text__contains: hello}, traverse_on: [chunks, matches], depth_range: [0, 2]}'))

        with f:
            f.index(random_docs(10), output_fn=validate, callback_on_body=True)


if __name__ == '__main__':
    unittest.main()
