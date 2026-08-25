import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import {
  createPortal,
} from "react-dom";


const PREVIEW_GAP = 14;
const VIEWPORT_PADDING = 16;


export function IPriceProductImage({
  src,
  alt,
  caption,
  className = "iprice-row-image",
  placeholderClassName = "iprice-row-image-placeholder",
  placeholderText = "Нет фото",
}) {
  const [failedSrc, setFailedSrc] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewPosition, setPreviewPosition] = useState(null);
  const anchorRef = useRef(null);
  const previewRef = useRef(null);

  const hasError = failedSrc === src;

  const hidePreview = () => {
    setShowPreview(false);
    setPreviewPosition(null);
  };

  const updatePreviewPosition = useCallback(() => {
    if (!anchorRef.current || !previewRef.current) {
      return;
    }

    const anchorRect = anchorRef.current.getBoundingClientRect();
    const previewRect = previewRef.current.getBoundingClientRect();
    const spaceOnRight = window.innerWidth - anchorRect.right;
    const placeOnRight = (
      spaceOnRight >= previewRect.width + PREVIEW_GAP
      || anchorRect.left < spaceOnRight
    );
    const requestedLeft = placeOnRight
      ? anchorRect.right + PREVIEW_GAP
      : anchorRect.left - previewRect.width - PREVIEW_GAP;
    const requestedTop = (
      anchorRect.top
      + (anchorRect.height - previewRect.height) / 2
    );
    const maxLeft = (
      window.innerWidth
      - previewRect.width
      - VIEWPORT_PADDING
    );
    const maxTop = (
      window.innerHeight
      - previewRect.height
      - VIEWPORT_PADDING
    );

    setPreviewPosition({
      left: Math.max(
        VIEWPORT_PADDING,
        Math.min(requestedLeft, maxLeft),
      ),
      top: Math.max(
        VIEWPORT_PADDING,
        Math.min(requestedTop, maxTop),
      ),
    });
  }, []);

  useLayoutEffect(() => {
    if (!showPreview) {
      return undefined;
    }

    updatePreviewPosition();
    window.addEventListener("resize", updatePreviewPosition);
    window.addEventListener(
      "scroll",
      updatePreviewPosition,
      true,
    );

    return () => {
      window.removeEventListener(
        "resize",
        updatePreviewPosition,
      );
      window.removeEventListener(
        "scroll",
        updatePreviewPosition,
        true,
      );
    };
  }, [showPreview, updatePreviewPosition]);

  if (!src || hasError) {
    return (
      <div className={placeholderClassName}>
        {placeholderText}
      </div>
    );
  }

  return (
    <>
      <span
        ref={anchorRef}
        className="iprice-product-image-trigger"
        tabIndex={0}
        onMouseEnter={() => setShowPreview(true)}
        onMouseLeave={hidePreview}
        onFocus={() => setShowPreview(true)}
        onBlur={hidePreview}
      >
        <img
          src={src}
          alt={alt || ""}
          loading="lazy"
          className={className}
          onError={() => {
            setFailedSrc(src);
            hidePreview();
          }}
        />
      </span>

      {showPreview && createPortal(
        <div
          ref={previewRef}
          className={(
            "iprice-product-image-preview"
            + (previewPosition
              ? " iprice-product-image-preview--positioned"
              : "")
          )}
          style={previewPosition || undefined}
          role="tooltip"
        >
          <img src={src} alt="" />

          {(caption || alt) && (
            <div className="iprice-product-image-preview__caption">
              {caption || alt}
            </div>
          )}
        </div>,
        document.body,
      )}
    </>
  );
}
