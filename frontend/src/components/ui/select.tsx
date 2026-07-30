import { ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative inline-flex">
      <select
        data-slot="select"
        className={cn(
          "border-input flex h-9 w-full min-w-0 appearance-none rounded-md border bg-transparent px-3 py-1 pr-8 text-sm shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="text-muted-foreground pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2"
        aria-hidden="true"
      />
    </div>
  );
}

export { Select };
