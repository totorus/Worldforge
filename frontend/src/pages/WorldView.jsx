import { useParams } from "react-router-dom";

export default function WorldView() {
  const { worldId } = useParams();
  return <div><h1>Monde — {worldId}</h1></div>;
}
