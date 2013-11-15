#!/usr/bin/env python
import os
import re
import urlparse

from flask import Flask, render_template, send_from_directory

# initialization
app = Flask(__name__)

#app.config.update(
#    DEBUG = True,
#)

# controllers
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'ico/favicon.ico')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route("/")
def index():
    return render_template('index.html')

def extract_service_domain_from_link(link):
    domain = urlparse.urlparse(link).netloc
    if re.match('^[^.]+\.service\.gov\.uk$',domain):
        return True, domain
    else:
        return False, "The link is not to something on the service.gov.uk domain"

def find_domain_from_slug(govuk_slug):
    link = 'https://foo.service.gov.uk/start'
    return True, link

def check_bare_ssl_domain_redirects_to_slug(domain, slug):
    message = "Check that https://%s redirects to https://www.gov.uk/%s" % (domain, slug)
    return True, message

def check_listening_on_http(slug,domain):
    message = "Check that requests for http://%s are denied or redirected to https://$s" % (domain, domain)
    return True, message

def check_for_HSTS_header(slug,domain):
    message = "Check that Strict-Transport-Security is enforced"
    return True, message

def check_for_robots_txt(domain):
    message = "Check that https://%s/robots.txt exists"
    return True, message

def check_cookies(link):
    message = "Checking cookies are HttpOnly, Secure and scoped to the domain"
    return True, message

# launch
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
