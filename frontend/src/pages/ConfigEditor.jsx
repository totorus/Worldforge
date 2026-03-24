import { useParams } from "react-router-dom";

export default function ConfigEditor() {
  const { worldId } = useParams();
  return <div><h1>Configuration — {worldId}</h1></div>;
}
