import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/** Surface primitive for workspace cards (styles live in globals.css `.panel*`). */
const panelVariants = cva("panel", {
  variants: {
    variant: {
      default: "",
      interactive: "panel-interactive",
      inset: "panel-inset",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface PanelProps
  extends React.HTMLAttributes<HTMLElement>, VariantProps<typeof panelVariants> {
  as?: "div" | "section" | "article" | "li";
}

const Panel = React.forwardRef<HTMLElement, PanelProps>(
  ({ className, variant, as: Tag = "div", ...props }, ref) => (
    <Tag
      ref={ref as React.Ref<never>}
      className={cn(panelVariants({ variant }), className)}
      {...props}
    />
  ),
);
Panel.displayName = "Panel";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn(panelVariants(), className)} {...props} />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("leading-none font-semibold tracking-tight", className)}
      {...props}
    />
  ),
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("text-muted-foreground text-sm", className)} {...props} />
  ),
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  ),
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  ),
);
CardFooter.displayName = "CardFooter";

export {
  Panel,
  panelVariants,
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardDescription,
  CardContent,
};
