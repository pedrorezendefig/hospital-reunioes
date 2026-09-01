"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { PARAM_DESTINO, destinoAposLogin } from "@/lib/login/destino";

export async function login(formData: FormData) {
  const supabase = await createClient();

  const { error } = await supabase.auth.signInWithPassword({
    email: formData.get("email") as string,
    password: formData.get("password") as string,
  });

  if (error) {
    return { error: error.message };
  }

  // O destino original, quando a pessoa chegou aqui por um link (issue #477).
  // Ele é medido de novo AQUI, mesmo a tela já tendo medido antes de montar o
  // campo: o valor viaja pelo formulário, ou seja, pelo cliente. A régua que
  // vale é a do lado que decide a navegação.
  redirect(destinoAposLogin(formData.get(PARAM_DESTINO)));
}

export async function logout() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
