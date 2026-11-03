/**
 * Jobs map (J161): collapsible, lazy-loaded Yandex Maps with list linkage.
 *
 * The external API is fetched only after the user (or the desktop default)
 * expands the map. Coordinates come from JSON scripts, never from the URL.
 */
(function () {
    'use strict';

    var block = document.getElementById('jobs-map-block');
    if (!block) return;

    var toggle = document.getElementById('jobs-map-toggle');
    var fullscreenBtn = document.getElementById('jobs-map-fullscreen');
    var collapseBtn = document.getElementById('jobs-map-collapse');
    var searchBtn = document.getElementById('jobs-map-search-area');
    var preview = document.getElementById('jobs-map-preview');
    var previewTitle = document.getElementById('jobs-map-preview-title');
    var previewMeta = document.getElementById('jobs-map-preview-meta');
    var previewLink = document.getElementById('jobs-map-preview-link');
    var previewClose = document.getElementById('jobs-map-preview-close');
    var pointsNode = document.getElementById('jobs-map-data');
    var geoNode = document.getElementById('jobs-geo-data');
    var points = pointsNode ? JSON.parse(pointsNode.textContent) : [];
    var geo = geoNode ? JSON.parse(geoNode.textContent) : null;
    var geoActive = block.getAttribute('data-geo-active') === 'true';
    var map = null;
    var clusterer = null;
    var byId = {};
    var ymapsPromise = null;
    var fullscreen = false;
    var mapReady = false;

    function label(name, fallback) {
        return block.getAttribute('data-label-' + name) || fallback;
    }

    function loadYmaps() {
        if (window.ymaps) {
            return Promise.resolve(window.ymaps);
        }
        if (ymapsPromise) return ymapsPromise;
        ymapsPromise = new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = 'https://api-maps.yandex.ru/2.1/?apikey=' +
                encodeURIComponent(block.getAttribute('data-api-key') || '') +
                '&lang=ru_RU';
            script.async = true;
            script.onload = function () {
                if (window.ymaps) resolve(window.ymaps);
                else reject(new Error('ymaps is unavailable'));
            };
            script.onerror = function () { reject(new Error('ymaps failed to load')); };
            document.head.appendChild(script);
        });
        return ymapsPromise;
    }

    function hidePreview() {
        if (preview) preview.classList.add('hidden');
    }

    function showPreview(point) {
        if (!preview) return;
        previewTitle.textContent = point.title || '';
        var parts = [];
        if (point.price) parts.push(point.price + ' ₽');
        if (point.org) parts.push(point.org);
        if (point.city) parts.push(point.city);
        if (point.when) parts.push(point.when);
        previewMeta.textContent = parts.join(' · ');
        previewLink.href = point.url;
        previewLink.textContent = label('open', 'Открыть задание');
        preview.classList.remove('hidden');
    }

    function setFullscreen(on) {
        fullscreen = on;
        block.classList.toggle('is-fullscreen', on);
        document.body.classList.toggle('jobs-map-lock', on);
        if (fullscreenBtn) {
            fullscreenBtn.setAttribute(
                'aria-label',
                label(on ? 'exit-fullscreen' : 'fullscreen', on ? 'Выйти из полноэкранного режима' : 'На весь экран')
            );
            fullscreenBtn.setAttribute(
                'title',
                label(on ? 'exit-fullscreen' : 'fullscreen', on ? 'Выйти из полноэкранного режима' : 'На весь экран')
            );
        }
        window.setTimeout(function () {
            if (map && map.container) map.container.fitToViewport();
        }, 60);
    }

    function setExpanded(open, remember) {
        block.classList.toggle('hidden', !open);
        if (toggle) {
            toggle.classList.remove('hidden');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.classList.toggle('is-active', open);
        }
        if (remember) {
            try {
                localStorage.setItem('trudnik-jobs-map-open', open ? '1' : '0');
            } catch (error) { /* private mode */ }
        }
        if (!open) {
            setFullscreen(false);
            hidePreview();
            return;
        }
        initMap();
    }

    function makePlacemark(ymaps, point) {
        var placemark = new ymaps.Placemark(
            [point.lat, point.lng],
            { hintContent: point.title || '' },
            { preset: 'islands#orangeIcon', hasBalloon: false }
        );
        placemark.events.add('click', function () { showPreview(point); });
        byId[point.id] = placemark;
        return placemark;
    }

    function zoomForRadius(radius) {
        if (radius <= 1) return 13;
        if (radius <= 5) return 12;
        if (radius <= 20) return 11;
        if (radius <= 50) return 10;
        return 9;
    }

    function buildMap(ymaps) {
        ymaps.ready(function () {
            map = new ymaps.Map('jobs-map', {
                center: geo ? [geo.lat, geo.lng] : [55.7558, 37.6173],
                zoom: geo ? zoomForRadius(geo.radius) : 10,
                controls: ['zoomControl']
            });
            // Do not hijack page scrolling: zoom via the +/- control or buttons.
            map.behaviors.disable('scrollZoom');

            if (geo) {
                map.geoObjects.add(new ymaps.Circle(
                    [[geo.lat, geo.lng], geo.radius * 1000],
                    {},
                    { fillColor: '#f59e0b22', strokeColor: '#d97706', strokeWidth: 2, strokeOpacity: 0.75 }
                ));
            }

            if (typeof ymaps.Clusterer === 'function') {
                clusterer = new ymaps.Clusterer({
                    preset: 'islands#orangeClusterIcons',
                    groupByCoordinates: false,
                    clusterDisableClickZoom: false
                });
            } else {
                clusterer = new ymaps.GeoObjectCollection();
            }
            points.forEach(function (point) {
                clusterer.add(makePlacemark(ymaps, point));
            });
            map.geoObjects.add(clusterer);

            if (geo) {
                map.setCenter([geo.lat, geo.lng], zoomForRadius(geo.radius));
            } else if (points.length === 1) {
                map.setCenter([points[0].lat, points[0].lng], 12);
            } else if (points.length > 1) {
                var bounds = clusterer.getBounds();
                if (bounds) map.setBounds(bounds, { checkZoomRange: true, zoomMargin: 40 });
            }

            map.events.add('actionend', function () {
                if (mapReady && searchBtn) searchBtn.classList.remove('hidden');
            });
            mapReady = true;

            // The Yandex logo is a link without an accessible name (axe link-name).
            (function labelLogo(tries) {
                var logo = document.querySelector('a[class*="copyright__logo"]');
                if (logo) {
                    if (!logo.getAttribute('aria-label')) {
                        logo.setAttribute('aria-label', label('yandex', 'Яндекс Карты'));
                    }
                    return;
                }
                if (tries > 0) window.setTimeout(function () { labelLogo(tries - 1); }, 300);
            })(20);
        });
    }

    function initMap() {
        if (map) {
            window.setTimeout(function () {
                if (map && map.container) map.container.fitToViewport();
            }, 30);
            return;
        }
        loadYmaps().then(buildMap).catch(function () {
            block.classList.add('hidden');
            if (toggle) toggle.classList.add('hidden');
        });
    }

    function searchArea() {
        if (!map || !window.ymaps) return;
        var center = map.getCenter();
        var bounds = map.getBounds();
        var radius = window.ymaps.coordSystem.geo.getDistance(center, bounds[1]) / 1000;
        radius = Math.min(100, Math.max(0.1, Math.round(radius * 10) / 10));
        var form = document.getElementById('geo-form');
        if (!form) return;
        document.getElementById('geo-lat').value = center[0].toFixed(6);
        document.getElementById('geo-lng').value = center[1].toFixed(6);
        document.getElementById('geo-radius').value = String(radius);
        var params = new URLSearchParams(window.location.search);
        params.set('geo', '1');
        params.set('radius', String(radius));
        params.delete('lat');
        params.delete('lng');
        params.delete('page');
        document.getElementById('geo-next').value =
            window.location.pathname + '?' + params.toString();
        form.submit();
    }

    function setHighlight(id, on) {
        var placemark = byId[id];
        if (!placemark) return;
        try {
            placemark.options.set('preset', on ? 'islands#redIcon' : 'islands#orangeIcon');
        } catch (error) { /* cluster may hide the icon */ }
    }

    document.querySelectorAll('[data-job-id]').forEach(function (card) {
        var id = card.getAttribute('data-job-id');
        card.addEventListener('mouseenter', function () { setHighlight(id, true); });
        card.addEventListener('mouseleave', function () { setHighlight(id, false); });
        card.addEventListener('focusin', function () { setHighlight(id, true); });
        card.addEventListener('focusout', function () { setHighlight(id, false); });
    });

    if (toggle) {
        toggle.addEventListener('click', function () {
            setExpanded(block.classList.contains('hidden'), true);
        });
    }
    if (collapseBtn) {
        collapseBtn.addEventListener('click', function () {
            setExpanded(false, true);
            if (toggle) toggle.focus();
        });
    }
    if (fullscreenBtn) fullscreenBtn.addEventListener('click', function () {
        setFullscreen(!fullscreen);
    });
    if (searchBtn) searchBtn.addEventListener('click', searchArea);
    if (previewClose) previewClose.addEventListener('click', hidePreview);
    if (previewLink) previewLink.addEventListener('click', hidePreview);
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        if (fullscreen) setFullscreen(false);
        else hidePreview();
    });

    var resizeTimer = null;
    window.addEventListener('resize', function () {
        if (!map) return;
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(function () {
            if (map && map.container) map.container.fitToViewport();
        }, 150);
    });

    var stored = null;
    try {
        stored = localStorage.getItem('trudnik-jobs-map-open');
    } catch (error) { /* private mode */ }
    var desktop = window.matchMedia && window.matchMedia('(min-width: 768px)').matches;
    var open = geoActive ? true : (stored === null ? desktop : stored === '1');
    setExpanded(open, false);
})();
