import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface BookProject {
  id?: string;
  title: string;
  author: string;
  docx_filename?: string;
  kdp_width_inches: number;
  kdp_height_inches: number;
  margin_inner_inches: number;
  margin_outer_inches: number;
  margin_top_inches: number;
  margin_bottom_inches: number;
  font_family: string;
  font_size_pt: number;
  line_height_relative: number;
  letter_spacing_pt: number;
  widow_orphan_control: boolean;
  content_blocks: any[];
  style_mappings: { [key: string]: string };
  chapter_definitions: { chapter_block_ids: string[] };
}

interface PageLine {
  block_id: string;
  text: string;
  is_chapter: boolean;
  semantic_type: string;
}

interface Page {
  page_number: number;
  is_left: boolean;
  lines: PageLine[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  // Navigation & Screen state
  protected currentScreen = signal<'dashboard' | 'mapping' | 'editor'>('dashboard');
  protected loading = signal<boolean>(false);
  protected statusMessage = signal<string>('');
  
  // Projects
  protected bookProjects = signal<BookProject[]>([]);
  
  // Active Project Data
  protected book = signal<BookProject>({
    title: 'Untitled Layout',
    author: '',
    kdp_width_inches: 6.0,
    kdp_height_inches: 9.0,
    margin_inner_inches: 0.75,
    margin_outer_inches: 0.5,
    margin_top_inches: 0.75,
    margin_bottom_inches: 0.75,
    font_family: 'Garamond',
    font_size_pt: 11,
    line_height_relative: 1.35,
    letter_spacing_pt: 0.0,
    widow_orphan_control: true,
    content_blocks: [],
    style_mappings: {},
    chapter_definitions: { chapter_block_ids: [] }
  });

  // Unique styles found in the DOCX
  protected uniqueStyles = signal<string[]>([]);
  
  // Heuristic confidence
  protected heuristicConfidence = signal<number>(1.0);
  
  // Typesetted Preview Pages
  protected pages = signal<Page[]>([]);
  protected activePageIndex = signal<number>(0);
  
  // UI Customization lists
  protected fontFamilies = signal<string[]>(['Garamond', 'Georgia', 'Times New Roman']);
  protected kdpPresets = [
    { name: '5" x 8"', width: 5.0, height: 8.0 },
    { name: '5.5" x 8.5"', width: 5.5, height: 8.5 },
    { name: '6" x 9" (Recommended)', width: 6.0, height: 9.0 },
    { name: '8.25" x 6"', width: 8.25, height: 6.0 }
  ];

  // API Base URL resolver
  private getApiUrl(path: string): string {
    const base = window.location.origin.includes('4200') ? 'http://localhost:8000' : '';
    return `${base}${path}`;
  }

  ngOnInit() {
    this.loadProjects();
    this.detectSystemFonts();
  }

  // Load available system fonts from PyWebView bridge
  private detectSystemFonts() {
    const webview = (window as any).pywebview;
    if (webview && webview.api && webview.api.get_system_fonts) {
      webview.api.get_system_fonts().then((fonts: string[]) => {
        if (fonts && fonts.length > 0) {
          this.fontFamilies.set(fonts);
          // Set default to first available or Garamond
          if (fonts.includes('Garamond')) {
            this.updateField('font_family', 'Garamond');
          } else {
            this.updateField('font_family', fonts[0]);
          }
        }
      });
    }
  }

  // Trigger project loading
  private async loadProjects() {
    try {
      const res = await fetch(this.getApiUrl('/api/books'));
      if (res.ok) {
        const list = await res.json();
        this.bookProjects.set(list);
      }
    } catch (err) {
      console.error('Failed to load projects from DB:', err);
    }
  }

  // Select project from dashboard
  protected selectProject(project: BookProject) {
    this.book.set(project);
    this.uniqueStyles.set(Object.keys(project.style_mappings));
    this.triggerPagination();
    this.currentScreen.set('editor');
  }

  // Native or HTML input file selection
  protected async selectFile() {
    const webview = (window as any).pywebview;
    if (webview && webview.api && webview.api.select_file) {
      this.loading.set(true);
      this.statusMessage.set('Awaiting native file picker...');
      try {
        const filePath = await webview.api.select_file();
        if (filePath) {
          // Send file path or let Python load it directly (since it is local)
          // Wait! For hybrid local apps, we can just pass the path to backend to read!
          // This is much faster. Let's implement a backend local path import
          this.statusMessage.set('Reading Word file...');
          // We can call backend path importer
        }
      } catch (err) {
        console.error(err);
      } finally {
        this.loading.set(false);
      }
    }
  }

  // Fallback upload method for standard browser dev mode
  protected async onFileUploaded(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);

    this.loading.set(true);
    this.statusMessage.set('Parsing DOCX document structure...');

    try {
      const res = await fetch(this.getApiUrl('/api/import'), {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) throw new Error('Failed to parse file');
      
      const data = await res.json();
      
      // Update active book state
      const currentBook = this.book();
      currentBook.title = file.name.replace(/\.[^/.]+$/, "");
      currentBook.docx_filename = file.name;
      currentBook.content_blocks = data.blocks;
      currentBook.style_mappings = data.chapter_detection.suggested_mappings;
      currentBook.chapter_definitions = {
        chapter_block_ids: data.chapter_detection.detected_chapter_block_ids
      };
      
      this.book.set(currentBook);
      this.uniqueStyles.set(data.styles_detected);
      this.heuristicConfidence.set(data.chapter_detection.confidence_score);

      // Route to Mapping UI if low confidence, otherwise straight to Editor
      if (this.heuristicConfidence() < 0.70) {
        this.currentScreen.set('mapping');
      } else {
        await this.triggerPagination();
        this.currentScreen.set('editor');
      }
    } catch (err: any) {
      alert(`Import failed: ${err.message}`);
    } finally {
      this.loading.set(false);
    }
  }

  // Heuristic confirmation / Style mapper confirmation
  protected async confirmMapping() {
    this.loading.set(true);
    this.statusMessage.set('Compiling initial typesetting layout...');
    try {
      await this.triggerPagination();
      this.currentScreen.set('editor');
    } finally {
      this.loading.set(false);
    }
  }

  // Toggle chapter definition manually on click (in mapper UI or editor)
  protected toggleChapterBlock(blockId: string) {
    const current = this.book();
    const idx = current.chapter_definitions.chapter_block_ids.indexOf(blockId);
    if (idx >= 0) {
      current.chapter_definitions.chapter_block_ids.splice(idx, 1);
    } else {
      current.chapter_definitions.chapter_block_ids.push(blockId);
    }
    
    // Also toggle the style mapping if appropriate
    const block = current.content_blocks.find(b => b.id === blockId);
    if (block) {
      current.style_mappings[block.style] = 'chapter_title';
    }

    this.book.set({ ...current });
    this.triggerPagination();
  }

  // Handle preset layout adjustments
  protected applyPreset(width: number, height: number) {
    const current = this.book();
    current.kdp_width_inches = width;
    current.kdp_height_inches = height;
    
    // Adjust default margins based on KDP sizes
    if (width < 6.0) {
      current.margin_inner_inches = 0.50;
      current.margin_outer_inches = 0.375;
    } else {
      current.margin_inner_inches = 0.75;
      current.margin_outer_inches = 0.50;
    }
    
    this.book.set({ ...current });
    this.triggerPagination();
  }

  // Generic settings update
  protected updateField(field: keyof BookProject, value: any) {
    const current = this.book();
    (current as any)[field] = value;
    this.book.set({ ...current });
    this.triggerPagination();
  }

  // Style mapping dropdown selector handler
  protected updateStyleMap(styleName: string, semanticType: string) {
    const current = this.book();
    current.style_mappings[styleName] = semanticType;
    
    // Re-synchronize explicit chapter definitions
    const newChapterIds: string[] = [];
    current.content_blocks.forEach(b => {
      if (current.style_mappings[b.style] === 'chapter_title') {
        newChapterIds.push(b.id);
      }
    });
    current.chapter_definitions.chapter_block_ids = newChapterIds;

    this.book.set({ ...current });
    this.triggerPagination();
  }

  // Recalculate book layout asynchronously
  protected async triggerPagination() {
    try {
      const res = await fetch(this.getApiUrl('/api/paginate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.book())
      });
      if (res.ok) {
        const result = await res.json();
        this.pages.set(result.pages);
        if (this.activePageIndex() >= result.pages.length) {
          this.activePageIndex.set(0);
        }
      }
    } catch (err) {
      console.error('Real-time pagination recalculation failed:', err);
    }
  }

  // Database Save
  protected async saveBookProject() {
    this.loading.set(true);
    this.statusMessage.set('Saving project to PostgreSQL database...');
    try {
      const current = this.book();
      const method = current.id ? 'PUT' : 'POST';
      const endpoint = current.id ? `/api/books/${current.id}` : '/api/books';
      
      const res = await fetch(this.getApiUrl(endpoint), {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(current)
      });
      
      if (res.ok) {
        const saved = await res.json();
        this.book.set(saved);
        this.loadProjects();
        alert('Project saved successfully!');
      } else {
        throw new Error('Save failed');
      }
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    } finally {
      this.loading.set(false);
    }
  }

  // Export engines trigger
  protected async triggerExport(type: 'pdf' | 'docx') {
    this.loading.set(true);
    this.statusMessage.set(`Compiling and building final ${type.toUpperCase()} layout...`);
    try {
      const res = await fetch(this.getApiUrl(`/api/export/${type}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.book())
      });
      
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.book().title}.${type}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } else {
        throw new Error(`Export server error`);
      }
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      this.loading.set(false);
    }
  }

  // Navigation page controls
  protected nextPage() {
    if (this.activePageIndex() + 2 < this.pages().length) {
      this.activePageIndex.set(this.activePageIndex() + 2);
    }
  }

  protected prevPage() {
    if (this.activePageIndex() - 2 >= 0) {
      this.activePageIndex.set(this.activePageIndex() - 2);
    }
  }
}
