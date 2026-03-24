import { useParams } from "react-router-dom";

export default function Timeline() {
  const { worldId } = useParams();
  return <div><h1>Chronologie — {worldId}</h1></div>;
}
