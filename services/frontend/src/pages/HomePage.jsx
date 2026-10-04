import { useWorkspace } from "../organizations/useWorkspace";
import { SelectMarketHome } from "../organizations/SelectMarketHome";

export function HomePage() {
  const workspace = useWorkspace();
  if (workspace?.organization.theme === "select-market") return <SelectMarketHome />;
  return (
    <>

      <div className="container">
        <div className="box-card">
          <div className="face front">iPlast</div>
          <div className="face back">iPlast</div>
          <div className="face right">iPlast</div>
          <div className="face left">iPlast</div>
          <div className="face top">iPlast</div>
          <div className="face bottom">iPlast</div>
        </div>
      </div>
    </>
  );
}
