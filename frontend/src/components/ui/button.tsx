import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    const variants = {
      primary: "bg-accent text-white hover:bg-accent-hover border border-accent/80",
      secondary: "bg-surface-elevated text-foreground hover:bg-slate-800 border border-border",
      ghost: "bg-transparent text-muted hover:text-foreground hover:bg-surface-elevated border border-transparent",
      danger: "bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/30",
    };
    const sizes = {
      sm: "h-8 px-3 text-xs",
      md: "h-9 px-4 text-sm",
      lg: "h-10 px-5 text-sm",
    };
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
