import { Badge, Flex, Text } from "@tremor/react";

interface Props {
  online: boolean;
  lastUpdate: string;
}

export function Header({ online, lastUpdate }: Props) {
  return (
    <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
      <div className="max-w-[1600px] mx-auto px-6 py-4">
        <Flex>
          <div>
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              🌊 <span>AQR Stream</span>
              <Badge color="blue" size="xs">v0.1</Badge>
            </h1>
            <Text className="text-xs text-gray-500">
              Continuous hypothesis generation engine
            </Text>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${online ? "bg-emerald-400 pulse-dot" : "bg-rose-500"}`} />
              <Text className="text-sm">
                {online ? "API online" : "offline"}
              </Text>
            </div>
            <Text className="text-xs text-gray-500">
              Обновлено: {lastUpdate}
            </Text>
          </div>
        </Flex>
      </div>
    </header>
  );
}
