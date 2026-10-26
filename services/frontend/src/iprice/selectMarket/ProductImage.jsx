import { IPriceProductImage } from "../components/IPriceProductImage";
export function ProductImage({ src, name }) {
  return <IPriceProductImage src={/^https?:\/\//i.test(src || "") ? src : null} alt={name || "Фото товара"} className="sm-product-image" placeholderClassName="sm-product-image sm-product-image-empty" />;
}
