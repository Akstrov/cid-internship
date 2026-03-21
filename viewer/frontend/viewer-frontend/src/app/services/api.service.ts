// src/app/services/api.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface PairSummary {
  _id: string;
  fiche: string;
  defect: string;
  page: number;
  layout: string;
  source_pdf: string;
}

export interface Commentary {
  full: string;
  intro: string;
  causes: string;
  gravite: string;
  suites: string;
}

export interface PairDetail extends PairSummary {
  commentary: Commentary;
  image_ext: string;
}

export interface PairsResponse {
  total: number;
  page: number;
  limit: number;
  pages: number;
  items: PairSummary[];
}

export interface StatusResponse {
  source: string;
  total: number;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = 'http://localhost:8000/api';

  constructor(private http: HttpClient) {}

  getStatus(): Observable<StatusResponse> {
    return this.http.get<StatusResponse>(`${this.base}/status`);
  }

  getPairs(page = 1, limit = 20, q = ''): Observable<PairsResponse> {
    let params = new HttpParams().set('page', page).set('limit', limit);
    if (q) params = params.set('q', q);
    return this.http.get<PairsResponse>(`${this.base}/pairs`, { params });
  }

  getPair(id: string): Observable<PairDetail> {
    return this.http.get<PairDetail>(`${this.base}/pairs/${id}`);
  }

  getImageUrl(id: string): string {
    return `${this.base}/pairs/${id}/image`;
  }

  createPair(formData: FormData): Observable<PairSummary> {
    return this.http.post<PairSummary>(`${this.base}/pairs`, formData);
  }
}
