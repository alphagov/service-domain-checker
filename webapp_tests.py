#!/usr/bin/env python
import os
import webapp
import unittest

class WebappTestExtractingServiceDomainsFromLinks(unittest.TestCase):

    #def setUp(self):
    #    self.app = webapp.app.test_client()

    def test_extract_service_domain_from_link(self):
        status, domain = webapp.extract_service_domain_from_link('https://foo.service.gov.uk/blah')
        assert True == status
        assert "foo.service.gov.uk" == domain


    def test_extract_nonservice_domain_from_link(self):
        status, domain = webapp.extract_service_domain_from_link('https://foo.foo.gov.uk/blah')
        assert False == status


class WebappTestExtractingServiceLinkFromSlug(unittest.TestCase):

    def test_find_link_from_slug(self):
        status, link = webapp.find_link_from_slug('/lasting-power-of-attorney')
        assert True == status
        assert "https://lastingpowerofattorney.service.gov.uk/" == link

    def test_fail_to_find_link_from_slug(self):
        status, link = webapp.find_link_from_slug('/bank-holidays')
        assert False == status


if __name__ == '__main__':
    unittest.main()
