import { Term } from "./ui/Term";

const colors = { черный: "#202124", белый: "#fff", серый: "#92979d", графитовый: "#4b5058", красный: "#d74646", синий: "#356fc0", голубой: "#7dc6eb", зеленый: "#479353", желтый: "#f2cb40", оранжевый: "#ef953e", коричневый: "#875d44", бежевый: "#d7c5a1", фиолетовый: "#8b63b5", розовый: "#e8a0bb", прозрачный: "#e9f5f8" };
export function ColorSwatch({ color }) {
  const value = String(color || "").trim().toLowerCase().replaceAll("ё", "е");
  const found = Object.entries(colors).filter(([name]) => value.includes(name)).map(([, hex]) => hex);
  const palette = found.length ? found : ["#d74646", "#efc945", "#479353", "#356fc0", "#8b63b5"];
  const background = palette.length === 1 ? palette[0] : `conic-gradient(${palette.map((hex, i) => `${hex} ${i * 100 / palette.length}% ${(i + 1) * 100 / palette.length}%`).join(",")})`;
  return <Term text={color || "Цвет не указан"}><span className="sm-color-swatch" aria-label={`Цвет: ${color || "не указан"}`} style={{ background }} /></Term>;
}
