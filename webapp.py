#!/usr/bin/env python
import gevent
import os
import re
import threading
import urllib2
import urlparse

from gevent import monkey; monkey.patch_all()

from flask import Flask, render_template, send_from_directory
from lxml.html import parse

# initialization
app = Flask(__name__)

app.config.update(
    DEBUG = True,
)

# controllers
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'ico/favicon.ico')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route("/")
def index():
    slug = '/lasting-power-of-attorney'
    return service_check(slug)


@app.route("/slug/<path:slug>")
def check(slug):
    return service_check("/%s" % slug)

# Main logic process

def service_check(slug):

    output = "<table>"
    result, link = find_link_from_slug(slug)
    if result:
        output += format_output(result, "Start page (https://www.gov.uk%s) links to the service (%s)" % (slug, link))
        result, domain = extract_service_domain_from_link(link)
        if result:
            check1 = gevent.spawn(check_bare_ssl_domain_redirects_to_slug, domain, slug)
            check2 = gevent.spawn(check_listening_on_http, domain)
            check3 = gevent.spawn(check_for_HSTS_header,link)
            check4 = gevent.spawn(check_for_robots_txt,domain)
            check5 = gevent.spawn(check_cookies,link)
            checks = [check1, check2, check3, check4, check5]
            gevent.joinall(checks)
            for check in checks:
                output += "%s\n" % check.value
        else:
            output += format_output(result, domain)
    else:
        output += format_output(result, link)
    output += "</table>"
    return output


# Helper functions
def extract_service_domain_from_link(link):
    domain = urlparse.urlparse(link).netloc
    if re.match('^.*\.service\.gov\.uk$',domain):
        return True, domain
    else:
        return False, "The link is not to something on the service.gov.uk domain"


def find_link_from_slug(govuk_slug):

    service_link = None
    html = urllib2.urlopen("https://www.gov.uk%s" % govuk_slug)
    doc = parse(html).getroot()
    for link in doc.cssselect('a'):
        if link.text_content() == 'Start now':
            service_link = link.get('href')
    if service_link != None:
        return True, service_link
    else:
        return False, "Could not find 'Start now' link on https://www.gov.uk%s" % govuk_slug



def header_dict(headers):
    dict = {}
    for header in headers:
        key, value = header.split(': ', 1)
        dict[key.lower()] = value.rstrip()
    return dict


def format_output(status, message):
    if status:
        return "<tr><td><span style='color: green;'>PASS</span></td><td>%s</td></tr>" % message
    else:
        return "<tr><td><span style='color: red;'>FAIL</span></td><td>%s</td></tr>" % message


# Service checks
def check_bare_ssl_domain_redirects_to_slug(domain, slug):
    correct_location = "https://www.gov.uk%s" % slug
    bare_domain = "https://%s/" % domain
    url = urllib2.urlopen(bare_domain)
    location = url.geturl()
    correct_location = "https://www.gov.uk%s" % slug
    if location == correct_location:
        return format_output(True, "The bare service domain (%s) should redirect back to the GOV.UK start page (%s)" % (bare_domain, correct_location))
    else:
        return format_output(False, "The bare service domain (%s) should redirect back to the GOV.UK start page (%s)" % (bare_domain, correct_location))


def check_listening_on_http(domain):
    try:
        url = urllib2.urlopen("http://%s/" % domain, timeout=2)
        location = url.geturl()
        ssl_location = "https://%s/" % domain
        if location == ssl_location:
            return format_output(True, "The service should only respond to HTTPS requests (Service redirects HTTP to HTTPS)")
        else:
            return format_output(False, "The service responds to HTTP requests and does not redirect them to HTTPS")
    except IOError:
        return format_output(True, "The service should only respond to HTTPS requests (Service does not listen on HTTP)")


def check_for_HSTS_header(link):
    try:
        url = urllib2.urlopen(link)
        headers = header_dict(url.info().headers)
        if 'strict-transport-security' in headers.keys():
            return format_output(True, "The service should set a Strict-Transport-Security (HSTS) header")
        else:
            return format_output(False, "The service should set a Strict-Transport-Security (HSTS) header")
    except urllib2.HTTPError as e:
        return format_output(False, "Error: %s" % e)


def check_for_robots_txt(domain):
    try:
        url = urllib2.urlopen("https://%s/robots.txt" % domain)
        headers = header_dict(url.info().headers)
        if headers['content-type'] == "text/plain":
            return format_output(True, "The service should have a robots.txt file to avoid appearing in search engines")
        else:
            return format_output(False, "The service has a robots.txt file, but it is not served as 'text/plain' (%s)" % headers['content-type'])
    except urllib2.HTTPError as e:
        return format_output(False, "The service should have a robots.txt file to avoid appearing in search engines: %s" % e)


def check_cookies(link):
    failed = False
    message = "Cookies should be Secure, HttpOnly and scoped to the service domain<br />"
    result, domain = extract_service_domain_from_link(link)
    cookie_domain = "domain=" + domain
    url = urllib2.urlopen(link)
    headers = url.info().headers
    for header in headers:
        key, value = header.rstrip().split(': ', 1)
        if key.lower() == 'set-cookie':
            cookie_settings = value.lower().split('; ')
            if 'httponly' not in cookie_settings:
                message += "HttpOnly is not set<br /><"
                message += "&nbsp;&nbsp;Set-Cookie: %s<br />" % value
                failed = True
            if 'secure' not in cookie_settings:
                message += "Secure is not set<br />"
                message += "&nbsp;&nbsp;Set-Cookie: %s<br />" % value
                failed = True
            if cookie_domain not in cookie_settings:
                message += "Cookie not scoped to domain=%s<br />" % domain
                message += "&nbsp;&nbsp;Set-Cookie: %s<br />" % value
                failed = True
    if failed:
        return format_output(False, message)
    else:
        return format_output(True, "Cookies are Secure, HttpOnly and scoped to the service domain")


# launch
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
