//
//   Copyright 2014 by mathias herzog, <mathu at gmx dot ch>
//
//   Licensed under the Apache License, Version 2.0 (the "License");
//   you may not use this file except in compliance with the License.
//   You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
//   Unless required by applicable law or agreed to in writing, software
//   distributed under the License is distributed on an "AS IS" BASIS,
//   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//   See the License for the specific language governing permissions and
//   limitations under the License.
//

define(function(require, exports, module) {
    var _ = require('underscore');
    var mvc = require('splunkjs/mvc');

    require("./jquery.bxslider");
    require("css!./jquery.bxslider.css");

    var SimpleSplunkView = require('splunkjs/mvc/simplesplunkview');
    var ImagePanelRandom = SimpleSplunkView.extend({
        className: "imagepanelrandom",
        options: {
            managerid: null,
            data: "preview",
            urlField: null
        },

        createView: function() {
            this.$el.html('');
            return true;
        },

        updateView: function(viz, data) {
            $el = this.$el
            // console.log("The data object: ", data);
            // get settings from simple xml
            var collection = data;
            var url = this.settings.get('urlField') || [];
            var auto = this.settings.get('autoField') || true;
            var mode = this.settings.get('modeField') || "vertical";
            var pager = this.settings.get('pagerField') || false;
            var speed = this.settings.get('speedField') || 2000;
            var adaptiveHeight = this.settings.get('adaptiveHeightField') || false;
            var randomStart = this.settings.get('randomStartField') || false;


            // create ul tag with class for bxslider
            var ul = $('<ul></ul>');
            ul.attr('class', "bxslider");

            // create li tag for every url found in the search
            for (var i=0; i < collection.length; i++){
              var li = $('<li></li>');
              // TODO: collection[i][0] is totally ugly and buggy
              //       -> correctt this!!
              var img = $('<img src="'+collection[i][0]+'" />');
              //var img = $('<img src="/static/app/custom_simplexml_extensions/custom_pics/pic1.jpg" />');
              img.attr('width', '92%');
              img.appendTo(li);
              li.appendTo(ul);
            }

            // append ul tag to DOM
            ul.appendTo($el);

            $('.bxslider').bxSlider({
              mode: mode,
              auto: auto,
              pause: 5000,
              randomStart: randomStart,
              autoControls: true,
              speed: speed,
              adaptiveHeight: adaptiveHeight,
              pager: pager
            });

        }
    });
    return ImagePanelRandom;
});
