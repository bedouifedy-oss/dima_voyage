// core/static/js/airport_search.js

(function() {
    function initAirportSearch() {
        // 1. Try to find a jQuery instance with .autocomplete()
        var $ = null;

        if (window.jQuery && typeof window.jQuery.fn.autocomplete === 'function') {
            $ = window.jQuery;
        } else if (window.$ && typeof window.$.fn.autocomplete === 'function') {
            $ = window.$;
        } else if (django.jQuery && typeof django.jQuery.fn.autocomplete === 'function') {
            $ = django.jQuery;
        }

        // If we still can't find it, log it clearly but DON'T retry infinitely
        if (!$) {
            console.warn("⚠️ Amadeus Search: jQuery UI Autocomplete function missing.");
            console.log("Debug Info:", {
                "window.jQuery": !!window.jQuery,
                "window.$": !!window.$,
                "django.jQuery": !!django.jQuery,
                "window.jQuery.fn.autocomplete": window.jQuery ? !!window.jQuery.fn.autocomplete : false
            });
            return; 
        }

        console.log("✅ Amadeus Search: jQuery UI loaded successfully.");

        // 2. Initialize
        const $field = $('#id_description'); 
        if ($field.length) {
            $field.autocomplete({
                source: "/api/airport-autocomplete/",
                minLength: 2,
                select: function(event, ui) {
                    $field.val(ui.item.value); 
                    return false;
                }
            });
            $field.attr('placeholder', '✈️ Search Airport (e.g. TUN, PAR)...');
            $field.css('border', '2px solid #4f46e5');
        }
    }

    // Wait 1 second to ensure all scripts (including CDNs) are parsed
    setTimeout(initAirportSearch, 1000);
})();
