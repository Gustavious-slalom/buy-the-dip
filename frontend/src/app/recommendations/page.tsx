import { RecommendationsView } from "@/components/recommendations/recommendations-view";

export default function RecommendationsPage() {
  return (
    <div style={{ minHeight: "calc(100vh - 36px)" }} className="reveal reveal-1">
      <RecommendationsView />
    </div>
  );
}
