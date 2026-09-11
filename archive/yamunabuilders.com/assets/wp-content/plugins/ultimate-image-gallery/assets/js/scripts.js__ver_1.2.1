;(function ($) {
	'use strict';
	jQuery(document).ready(function () {

		jQuery('.uig-img-viewer').each(function () {
			var thisParent = jQuery(this);
			var GalleryId = jQuery(this).attr('gallery_id');
			var parentClass = '.uig-img-viewer-'+GalleryId +'';
			var filterTarget = jQuery('.uig-gallery-item', this);
			var filterbutton = ''+parentClass+' .uig-filter-button';

			// View a list of images
			$('' + parentClass + ' .uig_zoom_gallery').viewer({
				inline: false,
				scalable: false,
				rotatable: false,
				movable: true,
				maxZoomRatio: 3,
			});
			
			jQuery('' + parentClass + ' .uig-filter-gallery-wrapper .uig_gallery_images').mixItUp({

			  	selectors: {
					target: filterTarget,
					filter: filterbutton,
//					sort: '.sort-btn'
			  	},
				animation: {
				  	animateResizeContainer: false,
				  	effects: 'fade scale'
				}

			});

			//Masonry scripts
			/*var masonrySelector = jQuery('' + parentClass + ' .uig_masonry_layout').length;
			if (masonrySelector > 0) {
				var grid = document.querySelector(parentClass + " .uig_gallery_images");
				var msnry;

				msnry = new Masonry(grid, {
					//options
					itemSelector: parentClass + " .uig-gallery-item",
					columnWidth: parentClass + " .uig-gallery-item-resizer",
					percentPosition: true
				});

				msnry.layout();

			}*/

			//Filter scripts
			/*jQuery('' + parentClass + ' .uig-filter-buttons button').on('click', function () {

				jQuery('' + parentClass + ' .uig-filter-buttons button').removeClass('uig-filter-active');
				jQuery(this).addClass('uig-filter-active');

				var category = jQuery(this).attr('data-filter');

				if (category == '*') {
					jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').show();

					if (masonrySelector == 0) {
						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').removeClass('hide-item');
					}

				} else {

					var hasclass = $('' + parentClass + ' .uig_gallery_images .uig-gallery-item').hasClass('hide-item');

					if (masonrySelector == 0) {

						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').addClass('hide-item');

						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').addClass('fadeout');
						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item.' + category + '').show();
						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item.' + category + '').removeClass('hide-item');

						if (!hasclass) {

							setTimeout(function () {
								jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item.hide-item').hide();
								jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').removeClass('fadeout');
							}, 150);

						} else {

							jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item.hide-item').hide();
							jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').removeClass('fadeout');
						}
					} else {
						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item').hide();
						jQuery('' + parentClass + ' .uig_gallery_images .uig-gallery-item.' + category + '').show();
					}

				}

			});*/

		});
	});

	//Fix masonry layout after loading images
	/*jQuery('.uig_gallery_images.uig_masonry_layout img').on('load', function () {
		jQuery('button.uig-filter-button.uig-filter-active').trigger('click');
	});*/

	//Wrap media buttons
	jQuery(document).on('click', '.uig-gallery-item', function () {
		jQuery('.viewer-container').each(function () {
			if (jQuery('.toolbar-top-buttons', this).length < 1) {
				jQuery('li.viewer-prev, li.viewer-play, li.viewer-next', this).wrapAll('<div class="toolbar-top-buttons"></div>');
			}
		});

	});

})(jQuery);