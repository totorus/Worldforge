import { useParams } from "react-router-dom";

export default function Narrative() {
  const { worldId } = useParams();
  return <div><h1>Narration — {worldId}</h1></div>;
}
