#!/usr/bin/env python
import datetime
import gevent
import os
import re
import urllib2
import urlparse

from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, send_from_directory, request, make_response
from lxml.html import parse

# initialization
app = Flask(__name__)

#app.config.update(
#    DEBUG=True,
#)

# controllers


@app.route('/favicon.ico')
def favicon():
    return add_cache_headers(send_from_directory(os.path.join(app.root_path, 'static'), 'ico/favicon.ico'), 30240)


@app.route('/css/<filename>')
def css(filename):
    return add_cache_headers(send_from_directory(os.path.join(app.root_path, 'static'), "css/%s" % filename), 30240)


@app.route('/js/<filename>')
def js(filename):
    return add_cache_headers(send_from_directory(os.path.join(app.root_path, 'static'), "js/%s" % filename), 30240)


@app.errorhandler(404)
def page_not_found():
    return add_cache_headers(render_template('404.html'), 30240), 404


@app.route("/")
def index():
    value = request.args.get('slug')
    if value is None:
        value = ""
    return add_cache_headers(render_template('index.html', value=value), 60)


@app.route("/about")
def about():
    return add_cache_headers(render_template('about.html'), 30240)


@app.route("/slug/<path:slug>")
def check(slug):
    return add_cache_headers(service_check("/%s" % slug), 5)


# Helper functions
def extract_service_domain_from_link(link):
    domain = urlparse.urlparse(link).netloc
    if re.match('^.*\.service\.gov\.uk$', domain):
        return True, domain
    else:
        return False, "The link is not to something on the service.gov.uk domain"


def find_link_from_slug(govuk_slug):
    try:
        service_link = None
        html = urllib2.urlopen("https://www.gov.uk%s" % govuk_slug)
        doc = parse(html).getroot()
        for link in doc.cssselect('.get-started a'):
            if link.text_content() == 'Start now':
                service_link = link.get('href')
        if service_link is not None:
            return True, service_link
        for form in doc.cssselect('form.get-started'):
            service_link = form.get('action')
        if service_link is not None:
            return True, service_link
        return False, "Could not find 'Start now' link on https://www.gov.uk%s" % govuk_slug
    except IOError:
        return False, "https://www.gov.uk%s" % govuk_slug


def header_dict(headers):
    dikt = {}
    for header in headers:
        key, value = header.split(': ', 1)
        dikt[key.lower()] = value.rstrip()
    return dikt


def format_output(status, title, description):
    return render_template('check.html', status=status, title=title, description=description)


def datetime_filter(datetime, format_string='%d/%m/%Y %H:%M'):
    return datetime.strftime(format_string)

app.jinja_env.filters['datetime'] = datetime_filter


def add_cache_headers(response, minutes):
    response = make_response(response)
    then = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    rfc822 = then.strftime("%a, %d %b %Y %H:%M:%S +0000")
    response.headers.add('Expires', rfc822)
    response.headers.add(
        'Cache-Control', 'public,max-age=%d' % int(60 * minutes))
    return response


# Service checks
def check_bare_ssl_domain_redirects_to_slug(domain, slug):
    correct_location = "https://www.gov.uk%s" % slug
    bare_domain = "https://%s/" % domain
    url = urllib2.urlopen(bare_domain)
    location = url.geturl()
    correct_location = "https://www.gov.uk%s" % slug
    check_title = "The bare service domain should redirect back to the GOV.UK start page"
    check_description = """
    In order to make sure that all transactions begin and end on GOV.UK, it is important that
    the bare domain (<a href='%s'>%s</a>) redirects back to the GOV.UK start page (<a href='%s'>%s</a>), so that if users are
    typing the URL from memory, they get a consistent user experience and their browser does
    not cache the wrong entry page.
    """ % (bare_domain, bare_domain, correct_location, correct_location)
    if location == correct_location:
        return True, check_title, check_description
    else:
        return False, check_title, check_description


def check_listening_on_http(domain):
    check_title = "The service should enforce SSL"
    check_description = """
    Users must have confidence that any information they are submitting to a service, including
    pages they visit, is not available to a 3rd-party. In order to enforce this, the service should
    either reject non-SSL connections, or should immediately redirect them to secured connection via SSL.
    """
    try:
        url = urllib2.urlopen("http://%s/" % domain, timeout=1)
        location = url.geturl()
        ssl_location = "https://%s/" % domain
        if location == ssl_location:
            return True, "%s (Service redirects HTTP to HTTPS)" % check_title, check_description
        else:
            return False, check_title, check_description
    except IOError:
        return True, "%s (Service does not listen on HTTP)" % check_title, check_description


def check_for_HSTS_header(link):

    check_title = "The service should set a Strict-Transport-Security (HSTS) header"
    check_description = """
    To reduce the chance that traffic for a user can be intercepted, the service
    should notify the browser that in future it should only use secure connections.
    It can do this by setting an HTTP Header called 'Strict-Transport-Security'.
    """
    try:
        url = urllib2.urlopen(link)
        headers = header_dict(url.info().headers)
        if 'strict-transport-security' in headers.keys():
            return True, check_title, check_description
        else:
            return False, check_title, check_description
    except urllib2.HTTPError as e:
        return False, check_title, "Error: %s" % e


def check_for_www(domain):
    check_title = "The service domain format should be www.{service}.service.gov.uk"
    check_description = """
    The Service Manual states that Users must interact with a single domain and that it
    will be www.{service}.service.gov.uk. It is permissible to create extra domains for
    example for Content Delivery Networks, Assets or Administration, however the user-facing
    domain should be prefixed by www.
    """
    if re.match('^www\.[^.]+\.service\.gov\.uk$', domain):
        return True, check_title, check_description
    else:
        return False, check_title, check_description


def check_for_robots_txt(domain):
    check_title = "The service should have a robots.txt file"
    check_description = """
    Every service hosted on a service.gov.uk domain must have a robots.txt file asking search engines
    not to index any part of the site. More details can be found on the <a href='http://www.robotstxt.org/faq/prevent.html'>Web Robots pages</a>
    """
    try:
        url = urllib2.urlopen("https://%s/robots.txt" % domain)
        headers = header_dict(url.info().headers)
        if headers['content-type'].startswith("text/plain"):
            return True, check_title, check_description
        else:
            return False, check_title, "The robots.txt file exists, but is %s rather than text/plain." % headers['content-type']
    except urllib2.HTTPError as e:
        return False, check_title, "Could not find robots.txt (Error: %s)" % e


def check_cookies(link):
    failed = False
    check_title = "Cookies should be Secure, HttpOnly and scoped to the service domain"
    check_description = """
    Cookies used on www.{service}.service.gov.uk must be scoped to the originating domain only.
    Cookies must not be scoped to the domain servicename.service.gov.uk. Cookies must be sent with
    the <code>Secure</code> attribute and should, where appropriate, be sent with the <code>HttpOnly</code>
    attribute. These flags <a href='https://en.wikipedia.org/wiki/HTTP_cookie#Secure_and_HttpOnly'>provide additional assurances
    about how cookies will be handled by browsers.</a>
    """
    domain = extract_service_domain_from_link(link)[1]
    cookie_domain = "domain=" + domain
    url = urllib2.urlopen(link)
    headers = url.info().headers
    for header in headers:
        key, value = header.rstrip().split(': ', 1)
        if key.lower() == 'set-cookie':
            cookie_settings = value.lower().split('; ')
            if 'httponly' not in cookie_settings:
                check_description += "<br /><br />HttpOnly is not set<br /><"
                check_description += "&nbsp;&nbsp;Set-Cookie: %s<br />" % value
                failed = True
            if 'secure' not in cookie_settings:
                check_description += "<br /><br />Secure is not set<br />"
                check_description += "&nbsp;&nbsp;Set-Cookie: %s<br />" % value
                failed = True
            if cookie_domain not in cookie_settings:
                check_description += "<br /><br />Cookie not scoped to domain=%s<br />" % domain
                check_description += "&nbsp;&nbsp;Set-Cookie: %s<br />" % value
                failed = True
    if failed:
        return False, check_title, check_description
    else:
        return True, check_title, check_description


# Main logic process
def service_check(slug):


    output = ""
    result, link = find_link_from_slug(slug)
    if result:
        output += format_output(result,
                                "The GOV.UK start page should link to the service",
                                """All transactions should start on GOV.UK with a transaction start page.
                                You supplied the start page of <a href='https://www.gov.uk%s'>https://www.gov.uk%s</a>
                                which appears to link to a service: <a href='%s'>%s</a>
                                """ % (slug, slug, link, link))
        result, domain = extract_service_domain_from_link(link)
        if result:
            checks = [
                gevent.spawn(check_bare_ssl_domain_redirects_to_slug, domain, slug),
                gevent.spawn(check_listening_on_http, domain),
                gevent.spawn(check_for_www, domain),
                gevent.spawn(check_for_HSTS_header, link),
                gevent.spawn(check_for_robots_txt, domain),
                gevent.spawn(check_cookies, link)
            ]
            gevent.joinall(checks)
            for check in checks:
                status, message, description = check.value
                output += "%s\n" % format_output(status, message, description)
        else:
            output += format_output(result,
                                    "The GOV.UK start page should link to service on a service.gov.uk domain",
                                    """You supplied the start page of <a href='https://www.gov.uk%s'>https://www.gov.uk%s</a>
                                    which appears to have a 'Start now' button, but it does not link to something on the
                                    service.gov.uk domain as it points to <a href='%s'>%s</a>.""" % (slug, slug, link, link))
    else:
        output += format_output(result,
                                "The GOV.UK start page should link to the service",
                                """All transactions should start on GOV.UK with a transaction start page.
                                You supplied the start page of <a href='https://www.gov.uk%s'>https://www.gov.uk%s</a>,
                                but either the page does not exist, or I cannot find a 'Start now' link on this
                                page pointing to a service.""" % (slug, slug))
    return render_template('service_check.html', output=output, link=link, checked_at=datetime.datetime.now())


# launch
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
