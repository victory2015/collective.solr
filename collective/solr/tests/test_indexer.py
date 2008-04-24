from unittest import TestCase, TestSuite, makeSuite, main
from threading import Thread
from DateTime import DateTime

from collective.solr.manager import SolrConnectionManager
from collective.solr.indexer import SolrIndexQueueProcessor
from collective.solr.tests.utils import getData, fakehttp
from collective.solr.solr import SolrConnection


class Foo:
    """ dummy test object """
    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


class QueueIndexerTests(TestCase):

    def setUp(self):
        self.mngr = SolrConnectionManager()
        self.mngr.setHost(active=True)
        conn = self.mngr.getConnection()
        fakehttp(conn, getData('schema.xml'))       # fake schema response
        self.mngr.getSchema()                       # read and cache the schema
        self.proc = SolrIndexQueueProcessor(self.mngr)

    def tearDown(self):
        self.mngr.closeConnection()
        self.mngr.setHost(active=False)

    def testPrepareData(self):
        data = {'allowedRolesAndUsers': ['user:test_user_1_', 'user:portal_owner']}
        SolrIndexQueueProcessor().prepareData(data)
        self.assertEqual(data, {'allowedRolesAndUsers': ['user$test_user_1_', 'user$portal_owner']})

    def testIndexObject(self):
        response = getData('add_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)   # fake add response
        self.proc.index(Foo(id='500', name='python test doc'))   # indexing sends data
        self.assertEqual(str(output), getData('add_request.txt'))

    def testPartialIndexObject(self):
        foo = Foo(id='500', name='foo', price=42.0)
        # first index all attributes...
        response = getData('add_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)
        self.proc.index(foo)
        self.assert_(str(output).find('<field name="price">42.0</field>') > 0, '"price" data not found')
        # then only a subset...
        response = getData('add_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)
        self.proc.index(foo, attributes=['id', 'name'])
        output = str(output)
        self.assert_(output.find('<field name="name">foo</field>') > 0, '"name" data not found')
        self.assertEqual(output.find('price'), -1, '"price" data found?')
        self.assertEqual(output.find('42'), -1, '"price" data found?')

    def testDateIndexing(self):
        foo = Foo(id='zeidler', name='andi', cat='nerd', timestamp=DateTime('May 11 1972 03:45 GMT'))
        response = getData('add_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)   # fake add response
        self.proc.index(foo)
        required = '<field name="timestamp">1972-05-11T03:45:00.000Z</field>'
        self.assert_(str(output).find(required) > 0, '"date" data not found')

    def testReindexObject(self):
        response = getData('add_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)   # fake add response
        self.proc.reindex(Foo(id='500', name='python test doc')) # reindexing sends data
        self.assertEqual(str(output), getData('add_request.txt'))

    def testUnindexObject(self):
        response = getData('delete_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)   # fake response
        self.proc.unindex(Foo(id='500', name='python test doc')) # unindexing sends data
        self.assertEqual(str(output), getData('delete_request.txt'))

    def testCommit(self):
        response = getData('commit_response.txt')
        output = fakehttp(self.mngr.getConnection(), response)   # fake response
        self.proc.commit()                                       # committing sends data
        self.assertEqual(str(output), getData('commit_request.txt'))


class FakeHTTPConnectionTests(TestCase):

    def setUp(self):
        self.foo = Foo(id='500', name='python test doc')
        self.schema_request = 'GET /solr/admin/get-file.jsp?file=schema.xml'

    def testSingleRequest(self):
        mngr = SolrConnectionManager(active=True)
        output = fakehttp(mngr.getConnection(), getData('schema.xml'))
        mngr.getSchema()
        mngr.closeConnection()
        self.failUnless(output.get().startswith(self.schema_request))

    def testTwoRequests(self):
        mngr = SolrConnectionManager(active=True)
        proc = SolrIndexQueueProcessor(mngr)
        output = fakehttp(mngr.getConnection(), getData('schema.xml'),
            getData('add_response.txt'))
        proc.index(self.foo)
        mngr.closeConnection()
        self.assertEqual(len(output), 2)
        self.failUnless(output.get().startswith(self.schema_request))
        self.assertEqual(output.get(), getData('add_request.txt'))

    def testThreeRequests(self):
        mngr = SolrConnectionManager(active=True)
        proc = SolrIndexQueueProcessor(mngr)
        output = fakehttp(mngr.getConnection(), getData('schema.xml'),
            getData('add_response.txt'), getData('delete_response.txt'))
        proc.index(self.foo)
        proc.unindex(self.foo)
        mngr.closeConnection()
        self.assertEqual(len(output), 3)
        self.failUnless(output.get().startswith(self.schema_request))
        self.assertEqual(output.get(), getData('add_request.txt'))
        self.assertEqual(output.get(), getData('delete_request.txt'))

    def testFourRequests(self):
        mngr = SolrConnectionManager(active=True)
        proc = SolrIndexQueueProcessor(mngr)
        output = fakehttp(mngr.getConnection(), getData('schema.xml'),
            getData('add_response.txt'), getData('delete_response.txt'),
            getData('commit_response.txt'))
        proc.index(self.foo)
        proc.unindex(self.foo)
        proc.commit()
        mngr.closeConnection()
        self.assertEqual(len(output), 4)
        self.failUnless(output.get().startswith(self.schema_request))
        self.assertEqual(output.get(), getData('add_request.txt'))
        self.assertEqual(output.get(), getData('delete_request.txt'))
        self.assertEqual(output.get(), getData('commit_request.txt'))


class ThreadedConnectionTests(TestCase):

    def testLocalConnections(self):
        mngr = SolrConnectionManager(active=True)
        proc = SolrIndexQueueProcessor(mngr)
        mngr.setHost(active=True)
        schema = getData('schema.xml')
        log = []
        def runner():
            fakehttp(mngr.getConnection(), schema)      # fake schema response
            mngr.getSchema()                            # read and cache the schema
            response = getData('add_response.txt')
            output = fakehttp(mngr.getConnection(), response)   # fake add response
            proc.index(Foo(id='500', name='python test doc'))   # indexing sends data
            mngr.closeConnection()
            log.append(str(output))
            log.append(proc)
            log.append(mngr.getConnection())
        # after the runner was set up, another thread can be created and
        # started;  its output should contain the proper indexing request,
        # whereas the main thread's connection remain idle;  the latter
        # cannot be checked directly, but the connection object would raise
        # an exception if it was used to send a request without setting up
        # a fake response beforehand...
        thread = Thread(target=runner)
        thread.start()
        thread.join()
        conn = mngr.getConnection()         # get this thread's connection
        fakehttp(conn, schema)              # fake schema response
        mngr.getSchema()                    # read and cache the schema
        mngr.closeConnection()
        mngr.setHost(active=False)
        self.assertEqual(len(log), 3)
        self.assertEqual(log[0], getData('add_request.txt'))
        self.failUnless(isinstance(log[1], SolrIndexQueueProcessor))
        self.failUnless(isinstance(log[2], SolrConnection))
        self.failUnless(isinstance(proc, SolrIndexQueueProcessor))
        self.failUnless(isinstance(conn, SolrConnection))
        self.assertEqual(log[1], proc)      # processors should be the same...
        self.assertNotEqual(log[2], conn)   # but not the connections


def test_suite():
    return TestSuite([
        makeSuite(QueueIndexerTests),
        makeSuite(FakeHTTPConnectionTests),
        makeSuite(ThreadedConnectionTests),
    ])

if __name__ == '__main__':
    main(defaultTest='test_suite')

