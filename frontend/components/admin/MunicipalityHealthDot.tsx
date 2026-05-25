import type { MunicipalityHealth } from "@/lib/admin/municipalityOps";

const TONE_CLASSES: Record<MunicipalityHealth, string> = {
  healthy: "bg-emerald-500",
  degraded: "bg-amber-500",
  unhealthy: "bg-rose-500",
};

const LABEL: Record<MunicipalityHealth, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  unhealthy: "Unhealthy",
};

export function MunicipalityHealthDot({
  health,
}: {
  health: MunicipalityHealth;
}) {
  return (
    <span
      title={LABEL[health]}
      aria-label={LABEL[health]}
      className={[
        "inline-block h-2 w-2 rounded-full",
        TONE_CLASSES[health],
      ].join(" ")}
    />
  );
}
