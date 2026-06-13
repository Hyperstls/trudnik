from flask import Blueprint, Response, render_template

seo_bp = Blueprint('seo', __name__)


@seo_bp.route('/robots.txt')
def robots():
    return Response("User-agent: *\nAllow: /\nSitemap: https://trudnik.ru/sitemap.xml", mimetype='text/plain')


@seo_bp.route('/sitemap.xml')
def sitemap():
    pages = [
        {"loc": "/", "changefreq": "daily", "priority": "1.0"},
        {"loc": "/login", "changefreq": "monthly", "priority": "0.5"},
        {"loc": "/register", "changefreq": "monthly", "priority": "0.5"},
    ]
    sitemap_xml = render_template('sitemap.xml', pages=pages)
    return Response(sitemap_xml, mimetype='application/xml')
